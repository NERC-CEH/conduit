"""Configuration management for conduit."""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

import tomli_w

# Default pandas offset for a (from, to) frequency direction. The ``[[resample]]``
# preset falls back to this when no explicit ``freq`` is given; ``conduit.io`` also
# uses it as the cross-frequency temporal-alignment convention. It is a *default
# convention*, not a hard requirement — any direction is allowed with an explicit
# ``freq`` offset.
RESAMPLE_FREQ_MAP: dict[tuple[str, str], str] = {
    ("daily", "weekly"): "7D",
    ("daily", "monthly"): "1ME",
    ("weekly", "monthly"): "1ME",
}

_VALID_AGGFUNCS: frozenset[str] = frozenset(
    {"mean", "sum", "max", "min", "first", "last"}
)


@dataclass
class ResampleSpec:
    """Specification for a single [[resample]] entry.

    ``[[resample]]`` is a thin *preset* over the fan-out ``[[node]]`` mechanism: it
    desugars to one passthrough node per variable that applies
    `conduit.transforms.resample` (see `resample_to_node_entry`). ``freq`` is the
    pandas offset alias passed to that transform; when omitted it defaults from
    `RESAMPLE_FREQ_MAP` for the ``source_freq -> target_freq`` direction.
    """

    vars: list[str]
    source_freq: str
    target_freq: str
    aggfunc: str = "mean"
    freq: str | None = None

    @property
    def offset(self) -> str:
        """The resolved pandas offset: explicit ``freq`` or the direction default."""
        if self.freq is not None:
            return self.freq
        try:
            return RESAMPLE_FREQ_MAP[(self.source_freq, self.target_freq)]
        except KeyError:
            raise ValueError(
                f"No default offset for resample direction '{self.source_freq}' → "
                f"'{self.target_freq}'. Supported defaults: "
                f"{sorted(RESAMPLE_FREQ_MAP)}. Specify an explicit 'freq' "
                f"(pandas offset alias) instead."
            ) from None

    @classmethod
    def from_config(cls, entry: dict) -> "ResampleSpec":
        """Construct and validate from a raw [[resample]] TOML entry."""
        aggfunc = entry.get("aggfunc", "mean")
        if aggfunc not in _VALID_AGGFUNCS:
            raise ValueError(
                f"Unsupported aggfunc '{aggfunc}'. Supported: {sorted(_VALID_AGGFUNCS)}"
            )
        spec = cls(
            vars=entry["vars"],
            source_freq=entry["from_freq"],
            target_freq=entry["to_freq"],
            aggfunc=aggfunc,
            freq=entry.get("freq"),
        )
        _ = spec.offset  # validate the direction resolves (raises a clear message)
        return spec


@dataclass
class NodeSpec:
    """Specification for a single (already fan-out-expanded) [[node]] entry.

    ``units`` / ``dims`` / ``dtype`` / ``coords`` declare the node's output contract
    (read by the build-time contract check and stamped/validated at runtime). A
    ``passthrough`` node instead declares *no* fixed output contract and is tagged so
    the contract check propagates its input's declaration across it — the shape the
    ``[[resample]]`` preset generates.
    """

    name: str
    inputs: list[str]
    expression: str | None
    import_path: str | None
    function: str | None
    units: str | None = None
    dims: list[str] | None = None
    dtype: str | None = None
    coords: list[str] | None = None
    passthrough: bool = False

    @classmethod
    def from_config(cls, entry: dict) -> "NodeSpec":
        """Construct and validate from a raw (expanded) [[node]] TOML entry."""
        name = entry.get("name")
        has_expression = "expression" in entry
        has_function = "_import_path" in entry or "function" in entry
        if has_expression and has_function:
            raise ValueError(
                f"Node entry for '{name}' must specify either "
                "'expression' or ('_import_path' + 'function'), not both."
            )
        if not has_expression and not has_function:
            raise ValueError(
                f"Node entry for '{name}' must specify either "
                "'expression' or ('_import_path' + 'function')."
            )
        units = entry.get("units")
        if units is not None:
            # Fail fast on a malformed/unknown unit, at parse time.
            from xarray_annotated.units import assert_valid_unit

            assert_valid_unit(units, f"node '{name}' units")
        dtype = entry.get("dtype")
        if dtype is not None:
            import numpy as np

            try:
                np.dtype(dtype)
            except TypeError as exc:
                raise ValueError(f"node '{name}' has invalid dtype {dtype!r}.") from exc
        return cls(
            name=entry["name"],
            inputs=entry["inputs"],
            expression=entry.get("expression"),
            import_path=entry.get("_import_path"),
            function=entry.get("function"),
            units=units,
            dims=entry.get("dims"),
            dtype=dtype,
            coords=entry.get("coords"),
            passthrough=bool(entry.get("passthrough", False)),
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

    Each variable ``v`` becomes a node ``{v}_{target_freq}`` that applies
    `conduit.transforms.resample` to ``{v}_{source_freq}``; the node is a
    passthrough (unit/dim preserving), so the contract check propagates the
    source's declared contract across it.
    """
    src = f"{{var}}_{spec.source_freq}"
    return {
        "for_each": list(spec.vars),
        "name": f"{{var}}_{spec.target_freq}",
        "inputs": [src],
        "expression": (
            f"__transforms.resample({src}, freq={spec.offset!r}, "
            f"aggfunc={spec.aggfunc!r})"
        ),
        "passthrough": True,
    }


@dataclass
class CacheSpec:
    """Specification for the [cache] section.

    ``recompute`` and ``disable`` follow Hamilton's caching API: each is either
    a boolean (apply to all nodes) or a list of node names.
    """

    path: str = ".conduit_cache"
    recompute: bool | list[str] = field(default_factory=list)
    disable: bool | list[str] = field(default_factory=list)

    @classmethod
    def from_config(cls, entry: dict) -> "CacheSpec":
        """Construct and validate from a raw [cache] TOML entry."""

        def _coerce(key: str) -> bool | list[str]:
            val = entry.get(key, [])
            if isinstance(val, bool):
                return val
            if isinstance(val, list) and all(isinstance(v, str) for v in val):
                return val
            raise ValueError(
                f"[cache] '{key}' must be a boolean or a list of node names, "
                f"got {val!r}."
            )

        return cls(
            path=entry.get("path", ".conduit_cache"),
            recompute=_coerce("recompute"),
            disable=_coerce("disable"),
        )


@dataclass
class BlockingSpec:
    """Specification for the [blocking] section.

    Controls how a partition dimension (``dim``, default ``pixel``) is split into
    fixed-size sequential blocks to bound peak memory usage. Set ``dim`` to block
    over any other dimension (e.g. ``location``) for non-gridded pipelines.
    """

    block_size: int
    dim: str = "pixel"

    @classmethod
    def from_config(cls, entry: dict) -> "BlockingSpec":
        """Construct and validate from a raw [blocking] TOML entry."""
        block_size = entry.get("block_size")
        if not isinstance(block_size, int) or block_size < 1:
            raise ValueError(
                "[blocking] 'block_size' must be a positive integer, "
                f"got {block_size!r}."
            )
        dim = entry.get("dim", "pixel")
        if not isinstance(dim, str) or not dim:
            raise ValueError(
                f"[blocking] 'dim' must be a non-empty string, got {dim!r}."
            )
        return cls(block_size=block_size, dim=dim)


@dataclass
class SubsetSpec:
    """Specification for the [subset] section.

    Selects a contiguous slice of the stacked ``pixel`` dimension so that
    independent ``conduit run`` processes can each handle a different spatial
    chunk of the same input files.  ``pixel_end`` is exclusive (Python slice
    convention).
    """

    pixel_start: int
    pixel_end: int

    @classmethod
    def from_config(cls, entry: dict) -> "SubsetSpec":
        """Construct and validate from a raw [subset] TOML entry."""
        pixel_start = entry.get("pixel_start")
        pixel_end = entry.get("pixel_end")
        if not isinstance(pixel_start, int) or pixel_start < 0:
            raise ValueError(
                "[subset] 'pixel_start' must be a non-negative integer, "
                f"got {pixel_start!r}."
            )
        if not isinstance(pixel_end, int) or pixel_end < 0:
            raise ValueError(
                "[subset] 'pixel_end' must be a non-negative integer, "
                f"got {pixel_end!r}."
            )
        if pixel_end <= pixel_start:
            raise ValueError(
                f"[subset] 'pixel_end' ({pixel_end}) must be greater than "
                f"'pixel_start' ({pixel_start})."
            )
        return cls(pixel_start=pixel_start, pixel_end=pixel_end)


@dataclass
class IOSpec:
    """I/O specification for a single input or output section.

    ``vars`` maps this section's file variables to Hamilton node names, in one of
    two forms:

    - a **list** ``["temperature", ...]`` — the node name is derived from the file
      variable and the section's suffix (``{var}{suffix}``), the convenient default;
    - a **mapping** ``{node_name: file_var}`` — an explicit, suffix-free alias, e.g.
      ``{temperature_daily = "t2m"}`` (input: read file var ``t2m`` as node
      ``temperature_daily``) or ``{gpp_daily = "gpp"}`` (output: write node
      ``gpp_daily`` to file var ``gpp``). Use this to decouple file naming from DAG
      naming, or to alias a variable without renaming the file.

    ``suffix`` controls the list form's node names. When ``None`` (the default) the
    effective suffix is derived from the section label: ``_<label>`` for a
    temporal/grouped section, or ``""`` (bare names) for the conventional ``static``
    label. Set ``suffix = ""`` on any section for bare names, or ``suffix = "_x"``
    to choose an explicit suffix. It is ignored for the mapping form (which is
    already explicit). See ``conduit.io.effective_suffix``.
    """

    path: str
    vars: list[str] | dict[str, str]
    suffix: str | None = None


def _validate_vars(label: str, vars_: Any) -> list[str] | dict[str, str]:
    """Validate a section's ``vars`` is a list[str] or a dict[str, str]."""
    if isinstance(vars_, dict):
        bad = [
            (k, v)
            for k, v in vars_.items()
            if not isinstance(k, str) or not isinstance(v, str)
        ]
        if bad:
            raise ValueError(
                f"[{label}] 'vars' mapping must be {{node_name = file_var}} with "
                f"string keys and values, got offending entries {bad!r}."
            )
        return dict(vars_)
    if isinstance(vars_, list) and all(isinstance(v, str) for v in vars_):
        return list(vars_)
    raise ValueError(
        f"[{label}] 'vars' must be a list of names or a {{node_name = file_var}} "
        f"mapping, got {vars_!r}."
    )


@dataclass
class ParsedConfig:
    """Parsed pipeline configuration, ready to pass to build_driver."""

    modules: list[str]
    driver_config: dict[str, Any]
    input_specs: dict[str, "IOSpec"] = field(default_factory=dict)
    output_specs: dict[str, "IOSpec"] = field(default_factory=dict)
    cache_spec: "CacheSpec | None" = None
    blocking_spec: "BlockingSpec | None" = None
    subset_spec: "SubsetSpec | None" = None
    units_enabled: bool | None = None
    units_on_missing: str | None = None
    units_on_inexact: str | None = None
    schema_on_mismatch: str | None = None


class Config:
    """Configuration class with loading, parsing, and serialization."""

    def __init__(self, data: dict[str, Any]) -> None:
        """Initialize with a config dict."""
        self._data = data

    def __str__(self) -> str:
        """Return TOML string representation."""
        return self.dumps()

    @classmethod
    def load(cls, path: str | os.PathLike) -> Self:
        """Load config from a TOML file."""
        path = Path(path).resolve()
        with open(path, "rb") as f:
            data = tomllib.load(f)
        _resolve_paths(data, base=path.parent)
        return cls(data)

    @classmethod
    def loads(cls, toml_str: str) -> Self:
        """Load config from a TOML string."""
        return cls(tomllib.loads(toml_str))

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

    def _parse_grid(self, data: dict, driver_config: dict) -> list[str]:
        """Handle [grid] section.

        Silently accepted; grid computation moved to load_inputs().
        """
        data.pop("grid", None)
        return []

    def _parse_graphviz(self, data: dict, driver_config: dict) -> list[str]:
        """Handle a stray [graphviz] section.

        DAG-visualisation styling lives in its own file passed to ``conduit
        graph --style`` (see ``conduit.cli.graph_style``), not in the science
        config.  A misplaced [graphviz] section here is silently ignored rather
        than mistaken for an external module missing ``_import_path``.
        """
        data.pop("graphviz", None)
        return []

    def _parse_inputs(self, data: dict, driver_config: dict, input_specs: dict) -> None:
        """Handle [inputs.*] sections."""
        for freq, params in data.pop("inputs", {}).items():
            if "path" not in params:
                raise ValueError(
                    f"[inputs.{freq}] is missing a 'path' key. "
                    f"Input sections must specify a file path."
                )
            input_specs[freq] = IOSpec(
                path=params["path"],
                vars=_validate_vars(f"inputs.{freq}", params.get("vars") or []),
                suffix=params.get("suffix"),
            )

    def _parse_outputs(
        self, data: dict, driver_config: dict, output_specs: dict
    ) -> None:
        """Handle [outputs.*] sections."""
        for freq, params in data.pop("outputs", {}).items():
            vars_ = params.get("vars") or []
            if not vars_:
                raise ValueError(
                    f"[outputs.{freq}] has no 'vars'. "
                    f"Output sections must list at least one variable, "
                    f"or be removed from the config."
                )
            if "path" not in params:
                raise ValueError(
                    f"[outputs.{freq}] is missing a 'path' key. "
                    f"Output sections must specify a file path."
                )
            output_specs[freq] = IOSpec(
                path=params["path"],
                vars=_validate_vars(f"outputs.{freq}", vars_),
                suffix=params.get("suffix"),
            )

    def _parse_nodes(self, data: dict, driver_config: dict) -> list[str]:
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
        if specs:
            driver_config["node_specs"] = specs
            return ["node"]
        return []

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
        return CacheSpec.from_config(entry)

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

    def _parse_annotations(
        self, data: dict
    ) -> tuple[bool | None, str | None, str | None, str | None]:
        """Handle the [annotations] section (``[units]`` is a working alias).

        Returns ``(enabled, on_missing, on_inexact, on_mismatch)`` mapping the
        section's keys to the xarray-annotated policy axes:

        - ``mode`` (``strict`` / ``warn`` / ``off``) and ``exact`` (bool) drive the
          *units* policy (``enabled`` / ``on_missing`` / ``on_inexact``);
        - ``on_mismatch`` (``error`` / ``warn`` / ``ignore``) drives the *schema*
          (dims/coords/dtype) policy.

        ``mode = "off"`` disables validation for *every* facet via the shared
        master switch. ``None`` axes defer to the process-wide default. All are
        ``None`` if there is neither an [annotations] nor a [units] section.
        """
        annotations = data.pop("annotations", None)
        units = data.pop("units", None)
        if annotations is not None and units is not None:
            raise ValueError("Use either [annotations] or its alias [units], not both.")
        entry = annotations if annotations is not None else units
        if entry is None:
            return None, None, None, None
        label = "annotations" if annotations is not None else "units"
        enabled: bool | None = None
        on_missing: str | None = None
        on_inexact: str | None = None
        on_mismatch: str | None = None
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
        on_mismatch = entry.get("on_mismatch")
        if on_mismatch is not None and on_mismatch not in ("error", "warn", "ignore"):
            raise ValueError(
                f"[{label}] 'on_mismatch' must be one of 'error', 'warn', "
                f"'ignore', got {on_mismatch!r}."
            )
        return enabled, on_missing, on_inexact, on_mismatch

    def _parse_external_modules(self, data: dict, driver_config: dict) -> list[str]:
        """Handle remaining sections as external modules."""
        modules: list[str] = []
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
            _merge_params(section_label, params, driver_config)
            modules.append(import_path)
        return modules

    def parse(self) -> ParsedConfig:
        """Parse config into a ParsedConfig.

        Recognised top-level sections (processed directly):
        - [inputs.*]      — I/O specs; freq derived from subsection key
        - [outputs.*]     — I/O specs; freq derived from subsection key
        - [grid]          — silently accepted (grid computation is now in load_inputs())
        - [graphviz]      — silently ignored (DAG styling is a `graph --style` file)
        - [[node]]        — config-driven custom nodes (supports for_each fan-out)
        - [[resample]]    — preset desugaring to fan-out passthrough nodes
        - [cache]         — Hamilton result caching (path, recompute, disable)
        - [blocking]      — pixel-blocked execution (block_size)
        - [subset]        — spatial pixel slice (pixel_start, pixel_end)
        - [annotations]   — contract validation policy (units + schema); the
                            legacy name [units] is a working alias

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
        self._parse_grid(data, driver_config)
        self._parse_graphviz(data, driver_config)
        self._parse_inputs(data, driver_config, input_specs)
        self._parse_outputs(data, driver_config, output_specs)
        modules += self._parse_nodes(data, driver_config)
        cache_spec = self._parse_cache(data)
        blocking_spec = self._parse_blocking(data)
        subset_spec = self._parse_subset(data)
        (
            units_enabled,
            units_on_missing,
            units_on_inexact,
            schema_on_mismatch,
        ) = self._parse_annotations(data)
        modules += self._parse_external_modules(data, driver_config)
        return ParsedConfig(
            modules=modules,
            driver_config=driver_config,
            input_specs=input_specs,
            output_specs=output_specs,
            cache_spec=cache_spec,
            blocking_spec=blocking_spec,
            subset_spec=subset_spec,
            units_enabled=units_enabled,
            units_on_missing=units_on_missing,
            units_on_inexact=units_on_inexact,
            schema_on_mismatch=schema_on_mismatch,
        )


def load_config(config_path: str | Path) -> ParsedConfig:
    """Load and parse a TOML config file."""
    return Config.load(config_path).parse()


def _resolve_paths(data: dict, base: Path) -> None:
    """Resolve relative paths in-place, relative to the config file's directory."""
    for section in ("inputs", "outputs"):
        for params in data.get(section, {}).values():
            if "path" in params and not Path(params["path"]).is_absolute():
                params["path"] = str(base / params["path"])
    cache = data.get("cache")
    if cache and "path" in cache and not Path(cache["path"]).is_absolute():
        cache["path"] = str(base / cache["path"])


def _is_valid_module_path(path: str) -> bool:
    """Return True if path is a non-empty dotted Python identifier."""
    return bool(path) and all(part.isidentifier() for part in path.split("."))


def _merge_params(section: str, params: dict, driver_config: dict) -> None:
    """Merge params into driver_config, raising ValueError on key conflicts."""
    conflicts = set(params) & set(driver_config)
    if conflicts:
        raise ValueError(
            f"Parameter(s) {sorted(conflicts)} in [{section}] conflict "
            f"with an already-defined key. Use a module-specific prefix to "
            f"disambiguate (e.g. mymodel_threshold)."
        )
    driver_config |= params
