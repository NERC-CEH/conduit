"""Configuration management: parse a TOML file into a `ParsedConfig`.

The data model itself lives in `conduit.specs` (a leaf module); this module owns
the TOML -> spec translation: section dispatch, the `[[node]]` fan-out expansion,
the `[[resample]]` preset desugaring, and path resolution.
"""

import os
import tomllib
from dataclasses import replace
from pathlib import Path
from typing import Any, Self

import tomli_w

from .checks import CHECKS
from .specs import (
    AnnotationPolicySpec,
    BlockingSpec,
    CacheSpec,
    CheckSpec,
    IOSpec,
    NodeSpec,
    ParsedConfig,
    ResampleSpec,
    SubsetSpec,
    _severity,
    _validate_vars,
)


def expand_node_entries(entries: list[dict]) -> list[dict]:
    """Expand ``for_each`` fan-out entries into concrete per-variable node entries.

    An entry with ``for_each = ["a", "b"]`` produces one entry per value, with
    every ``{var}`` in its string fields (``name``, ``inputs``, ``expression``)
    substituted. Entries without ``for_each`` pass through unchanged. This is the
    config-level equivalent of Hamilton's ``@parameterize``.
    """
    out: list[dict] = []
    for entry in entries:
        for_each = entry.get("for_each")
        if not for_each:
            out.append(entry)
            continue
        for var in for_each:
            out.append(
                {k: _subst_var(v, var) for k, v in entry.items() if k != "for_each"}
            )
    return out


def _subst_var(value: Any, var: str) -> Any:
    """Substitute ``{var}`` in a string, or each string in a list."""
    if isinstance(value, str):
        return value.replace("{var}", var)
    if isinstance(value, list):
        return [x.replace("{var}", var) if isinstance(x, str) else x for x in value]
    return value


def resample_to_node_entry(spec: ResampleSpec) -> dict:
    """Desugar a `ResampleSpec` into a fan-out passthrough ``[[node]]`` entry.

    Each variable ``v`` becomes a node ``{v}_{target}`` applying
    `conduit.transforms.resample` to ``{v}_{source}``. The node is a **passthrough**
    but declares its own ``freq`` — the one facet a resample does not preserve — so
    every resample carries a checkable output-frequency contract, anchor included (a
    fat-fingered ``W-WED`` is caught at build time). See `conduit.dag.contract_check`.

    This preset is why ``[[resample]]`` needs no special-cased DAG module: it is an
    ordinary generated node.
    """
    src = f"{{var}}_{spec.source}"
    return {
        "for_each": list(spec.vars),
        "name": f"{{var}}_{spec.target}",
        "inputs": [src],
        "expression": (
            f"__transforms.resample({src}, freq={spec.freq!r}, "
            f"aggfunc={spec.aggfunc!r})"
        ),
        "freq": spec.freq,
        "passthrough": True,
    }


# ---------------------------------------------------------------------------
# The parser: raw TOML dict -> ParsedConfig
# ---------------------------------------------------------------------------


class Config:
    """Configuration class with loading, parsing, and serialization.

    The raw TOML data is held **exactly as written**: relative paths are resolved
    against ``base`` (the config file's directory) as the specs are built in `parse`,
    not by rewriting ``_data``. That keeps `dumps` round-trip faithful — it emits the
    relative paths the user wrote, not absolutised ones — and keeps `load` and `loads`
    behaving the same way apart from the base they resolve against.
    """

    def __init__(self, data: dict[str, Any], base: Path | None = None) -> None:
        """Initialize with a config dict, and the base its paths resolve against."""
        self._data = data
        self._base = base

    def __str__(self) -> str:
        """Return TOML string representation."""
        return self.dumps()

    @classmethod
    def load(cls, path: str | os.PathLike) -> Self:
        """Load a TOML file; relative paths resolve against its directory."""
        path = Path(path).resolve()
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls(data, base=path.parent)

    @classmethod
    def loads(cls, toml_str: str) -> Self:
        """Load config from a TOML string; relative paths resolve against the CWD."""
        return cls(tomllib.loads(toml_str))

    def _resolve(self, path: str) -> str:
        """Resolve one config path against the config file's directory."""
        if self._base is None or Path(path).is_absolute():
            return path
        return str(self._base / path)

    def dump(self, path: str | os.PathLike, overwrite_ok: bool = False) -> None:
        """Write config to a TOML file."""
        toml_str = self.dumps()
        path = Path(path)
        if path.exists() and not overwrite_ok:
            raise FileExistsError(
                f"There is already a file at {path}! "
                f"Consider passing `overwrite_ok=True`."
            )
        path.write_text(toml_str)

    def dumps(self) -> str:
        """Dump config to a TOML str."""
        return tomli_w.dumps(self._data)

    def _parse_inputs(self, data: dict, input_specs: dict) -> None:
        """Handle [inputs.*] sections.

        An input section may omit ``vars`` entirely, which binds every variable in
        the file through the section's suffix. It may not list *no* variables: an
        empty list previously parsed fine and then silently bound nothing.
        """
        for label, params in data.pop("inputs", {}).items():
            if "path" not in params:
                raise ValueError(
                    f"[inputs.{label}] is missing a 'path' key. "
                    f"Input sections must specify a file path."
                )
            vars_ = params.get("vars")
            if vars_ is not None and len(vars_) == 0:
                raise ValueError(
                    f"[inputs.{label}] has an empty 'vars'. Either list the "
                    f"variables to load, or omit 'vars' entirely to load every "
                    f"variable in the file."
                )
            input_specs[label] = IOSpec(
                path=self._resolve(params["path"]),
                vars=(
                    None if vars_ is None else _validate_vars(f"inputs.{label}", vars_)
                ),
                suffix=params.get("suffix"),
            )

    def _parse_outputs(self, data: dict, output_specs: dict) -> None:
        """Handle [outputs.*] sections."""
        for label, params in data.pop("outputs", {}).items():
            vars_ = params.get("vars") or []
            if not vars_:
                raise ValueError(
                    f"[outputs.{label}] has no 'vars'. "
                    f"Output sections must list at least one variable, "
                    f"or be removed from the config."
                )
            if "path" not in params:
                raise ValueError(
                    f"[outputs.{label}] is missing a 'path' key. "
                    f"Output sections must specify a file path."
                )
            output_specs[label] = IOSpec(
                path=self._resolve(params["path"]),
                vars=_validate_vars(f"outputs.{label}", vars_),
                suffix=params.get("suffix"),
            )

    def _parse_nodes(self, data: dict) -> list["NodeSpec"]:
        """Handle [[node]] and [[resample]] — both generate ``node`` module specs.

        ``[[resample]]`` is desugared to fan-out passthrough node entries
        (`resample_to_node_entry`), then all entries — inline and desugared — are
        fan-out-expanded (`expand_node_entries`) and built into `NodeSpec`s, with a
        single node-name-uniqueness check across the combined set.
        """
        entries: list[dict] = list(data.pop("node", []))
        for entry in data.pop("resample", []):
            entries.append(resample_to_node_entry(ResampleSpec.from_config(entry)))

        seen_names: set[str] = set()
        specs: list[NodeSpec] = []
        for concrete in expand_node_entries(entries):
            spec = NodeSpec.from_config(concrete)
            if spec.name in seen_names:
                raise ValueError(f"Duplicate node name '{spec.name}'")
            seen_names.add(spec.name)
            specs.append(spec)
        return specs

    def _parse_cache(self, data: dict) -> "CacheSpec | None":
        """Handle the [cache] section.

        Returns None if there is no [cache] section, or if it sets
        ``enabled = false``.
        """
        entry = data.pop("cache", None)
        if entry is None:
            return None
        if not entry.get("enabled", True):
            return None
        spec = CacheSpec.from_config(entry)
        return replace(spec, path=self._resolve(spec.path))

    def _parse_blocking(self, data: dict) -> "BlockingSpec | None":
        """Handle the [blocking] section.

        Returns None if there is no [blocking] section.
        """
        entry = data.pop("blocking", None)
        if entry is None:
            return None
        return BlockingSpec.from_config(entry)

    def _parse_subset(self, data: dict) -> "SubsetSpec | None":
        """Handle the [subset] section.

        Returns None if there is no [subset] section.
        """
        entry = data.pop("subset", None)
        if entry is None:
            return None
        return SubsetSpec.from_config(entry)

    def _parse_checks(
        self, data: dict, input_specs: dict[str, "IOSpec"]
    ) -> list["CheckSpec"]:
        """Handle the ``[validation]`` table's ``checks`` array.

        ``[validation]`` groups declared expectations to validate (as opposed to
        DAG structure). For each entry in its ``checks`` list this validates the
        check name (against the registry), expands ``["*"]`` to all input labels,
        checks every named input exists, and validates arity — all at parse time.
        Remaining inline-table keys become forwarded ``kwargs``.
        """
        section = data.pop("validation", {})
        unknown_keys = set(section) - {"checks"}
        if unknown_keys:
            raise ValueError(
                f"[validation] has unknown key(s) {sorted(unknown_keys)}; "
                f"only 'checks' is supported"
            )
        entries = section.get("checks", [])
        specs: list[CheckSpec] = []
        for entry in entries:
            entry = dict(entry)
            if "check" not in entry:
                raise ValueError(f"checks entry {entry!r} is missing a 'check' key")
            name = entry.pop("check")
            if name not in CHECKS:
                raise ValueError(
                    f"unknown check {name!r}; known checks: {sorted(CHECKS)}"
                )
            raw_inputs = entry.pop("inputs", None)
            if not raw_inputs:
                raise ValueError(f"check {name!r} is missing a non-empty 'inputs' list")

            if "*" in raw_inputs:
                if raw_inputs != ["*"]:
                    raise ValueError(
                        f"check {name!r}: '*' must be the sole element of 'inputs', "
                        f"got {raw_inputs!r}"
                    )
                inputs = list(input_specs)
            else:
                inputs = list(raw_inputs)
                unknown = [s for s in inputs if s not in input_specs]
                if unknown:
                    raise ValueError(
                        f"check {name!r} references unknown input section(s) "
                        f"{unknown}; known: {sorted(input_specs)}"
                    )

            arity = CHECKS[name].arity
            if arity != "variadic" and len(inputs) != arity:
                raise ValueError(
                    f"check {name!r} takes exactly {arity} input(s), "
                    f"got {len(inputs)}: {inputs}"
                )

            specs.append(CheckSpec(check=name, inputs=inputs, kwargs=entry))
        return specs

    def _parse_annotations(self, data: dict) -> "AnnotationPolicySpec":
        """Handle the [annotations] section.

        Maps the section's keys to the xarray-annotated policy axes:

        - ``mode`` (``strict`` / ``warn`` / ``off``) and ``exact`` (bool) drive the
          *units* policy (``enabled`` / ``on_missing`` / ``on_inexact``);
        - ``on_mismatch`` (``error`` / ``warn`` / ``ignore``) drives the *schema*
          (dims/coords/dtype) *and* *temporal* (freq) policies — in both it means
          "the array contradicts the declaration";
        - ``on_uninferable`` (``error`` / ``warn`` / ``ignore``) drives the temporal
          policy's second axis: a time axis too short or too irregular for a
          frequency to be inferred at all, so the declaration went *untested*.

        ``mode = "off"`` disables validation for *every* facet via the shared
        master switch. ``None`` axes defer to the process-wide default. All are
        ``None`` if there is no [annotations] section.
        """
        entry = data.pop("annotations", None)
        if entry is None:
            return AnnotationPolicySpec()
        label = "annotations"
        enabled: bool | None = None
        on_missing: str | None = None
        on_inexact: str | None = None
        mode = entry.get("mode")
        if mode is not None:
            if mode == "off":
                enabled = False
            elif mode == "strict":
                on_missing = "error"
            elif mode == "warn":
                on_missing = "warn"
            else:
                raise ValueError(
                    f"[{label}] 'mode' must be one of 'strict', 'warn', 'off', "
                    f"got {mode!r}."
                )
        exact = entry.get("exact")
        if exact is not None:
            if not isinstance(exact, bool):
                raise ValueError(f"[{label}] 'exact' must be a boolean, got {exact!r}.")
            if exact:
                on_inexact = "error"
        return AnnotationPolicySpec(
            enabled=enabled,
            on_missing=on_missing,
            on_inexact=on_inexact,
            on_mismatch=_severity(entry.get("on_mismatch"), label, "on_mismatch"),
            on_uninferable=_severity(
                entry.get("on_uninferable"), label, "on_uninferable"
            ),
        )

    def _parse_external_modules(self, data: dict, driver_config: dict) -> list[str]:
        """Handle remaining sections as external modules.

        Module params share one flat `driver_config` namespace (that is how Hamilton
        resolves a node's keyword-only config arguments), so ``defined_by`` tracks
        which section contributed each key — enough to name *both* sides of a
        collision rather than just the key.
        """
        modules: list[str] = []
        defined_by: dict[str, str] = {}
        for section_label, params in data.items():
            params = dict(params)
            import_path = params.pop("_import_path", None)
            if import_path is None:
                raise ValueError(
                    f"Section [{section_label!r}] is missing '_import_path'. "
                    f"All non-built-in sections must include "
                    f"'_import_path = \"pkg.module\"'."
                )
            if not _is_valid_module_path(import_path):
                raise ValueError(
                    f"'_import_path = {import_path!r}' in [{section_label!r}] "
                    f"is not a valid dotted module path."
                )
            _merge_params(section_label, params, driver_config, defined_by)
            modules.append(import_path)
        return modules

    def parse(self) -> ParsedConfig:
        """Parse config into a ParsedConfig.

        Recognised top-level sections (processed directly):
        - [inputs.*]      — I/O specs; freq derived from subsection key
        - [validation]    — declared expectations to validate; `checks` holds the
                            input-Dataset compatibility checks (see conduit.checks)
        - [outputs.*]     — I/O specs; freq derived from subsection key
        - [[node]]        — config-driven custom nodes (supports for_each fan-out)
        - [[resample]]    — preset desugaring to fan-out passthrough nodes
        - [cache]         — Hamilton result caching (path, recompute, disable)
        - [blocking]      — pixel-blocked execution (block_size)
        - [subset]        — a slice of one dimension (dim, start, stop)
        - [annotations]   — contract validation policy (units + schema + temporal)

        All other top-level sections are treated as external modules and must
        include a '_import_path = "pkg.module"' key specifying the importable
        module path. The key is stripped before merging remaining params into
        driver_config.
        """
        data = dict(self._data)
        driver_config: dict[str, Any] = {}
        input_specs: dict[str, IOSpec] = {}
        output_specs: dict[str, IOSpec] = {}
        modules: list[str] = []
        self._parse_inputs(data, input_specs)
        checks = self._parse_checks(data, input_specs)
        self._parse_outputs(data, output_specs)
        node_specs = self._parse_nodes(data)
        if node_specs:
            modules.append("node")
        cache_spec = self._parse_cache(data)
        blocking_spec = self._parse_blocking(data)
        subset_spec = self._parse_subset(data)
        annotations = self._parse_annotations(data)
        modules += self._parse_external_modules(data, driver_config)
        return ParsedConfig(
            modules=modules,
            driver_config=driver_config,
            node_specs=node_specs,
            input_specs=input_specs,
            output_specs=output_specs,
            cache_spec=cache_spec,
            blocking_spec=blocking_spec,
            subset_spec=subset_spec,
            checks=checks,
            annotations=annotations,
        )


# ---------------------------------------------------------------------------
# Module-level entry point + path/param utilities
# ---------------------------------------------------------------------------


def load_config(config_path: str | Path) -> ParsedConfig:
    """Load and parse a TOML config file."""
    return Config.load(config_path).parse()


def _is_valid_module_path(path: str) -> bool:
    """Return True if path is a non-empty dotted Python identifier."""
    return bool(path) and all(part.isidentifier() for part in path.split("."))


def _merge_params(
    section: str,
    params: dict,
    driver_config: dict,
    defined_by: dict[str, str],
) -> None:
    """Merge one section's params into the shared driver_config namespace.

    Raises on a key already contributed by another section, naming both — the user
    cannot fix a collision without knowing who they are colliding with.
    """
    for key in sorted(set(params) & set(driver_config)):
        raise ValueError(
            f"Parameter {key!r} is defined by both [{defined_by[key]}] and "
            f"[{section}]. Module parameters share one flat namespace, so give the "
            f"two parameters distinct names (e.g. {defined_by[key]}_{key} and "
            f"{section}_{key}) and rename the keyword argument in each module to "
            f"match."
        )
    driver_config |= params
    defined_by.update(dict.fromkeys(params, section))
