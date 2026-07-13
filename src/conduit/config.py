"""Configuration management for conduit."""

import keyword
import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Self, cast

import tomli_w

_VALID_AGGFUNCS: frozenset[str] = frozenset(
    {"mean", "sum", "max", "min", "first", "last"}
)


# ---------------------------------------------------------------------------
# Spec dataclasses (the parsed data model)
# ---------------------------------------------------------------------------


@dataclass
class ResampleSpec:
    """Specification for a single [[resample]] entry.

    ``[[resample]]`` is a thin *preset* over the fan-out ``[[node]]`` mechanism: it
    desugars to one passthrough node per variable that applies
    `conduit.transforms.resample` (see `resample_to_node_entry`).

    ``source`` and ``target`` (TOML ``from`` / ``to``) are **node-name suffixes**, not
    frequencies: ``from = "daily"`` reads ``{var}_daily`` and ``to = "weekly"``
    produces ``{var}_weekly``. They are free-form labels — ``from = "raw"``,
    ``to = "smoothed"`` is equally valid — and nothing is inferred from them. The
    frequency is ``freq`` alone: a required pandas offset alias, passed to the
    transform and declared as the generated node's output-frequency contract.
    """

    vars: list[str]
    source: str
    target: str
    freq: str
    aggfunc: str = "mean"

    @classmethod
    def from_config(cls, entry: dict) -> "ResampleSpec":
        """Construct and validate from a raw [[resample]] TOML entry."""
        aggfunc = entry.get("aggfunc", "mean")
        if aggfunc not in _VALID_AGGFUNCS:
            raise ValueError(
                f"Unsupported aggfunc '{aggfunc}'. Supported: {sorted(_VALID_AGGFUNCS)}"
            )
        missing = [key for key in ("vars", "from", "to", "freq") if key not in entry]
        if missing:
            raise ValueError(
                f"[[resample]] entry is missing required key(s) {missing}. Every "
                f"entry needs 'vars', 'from' and 'to' (the node-name suffixes to read "
                f"from and write to) and 'freq' (the target pandas offset alias, e.g. "
                f"'7D', '1ME', 'W-SUN')."
            )

        from xarray_annotated.temporal import Freq, assert_valid_freq

        freq = entry["freq"]
        assert_valid_freq(Freq(freq), f"[[resample]] to '{entry['to']}' freq")
        return cls(
            vars=entry["vars"],
            source=entry["from"],
            target=entry["to"],
            freq=freq,
            aggfunc=aggfunc,
        )


def _assert_node_identifier(value: Any, field_: str, node_name: Any) -> None:
    """Reject a node name / input that is unsafe to interpolate into node source.

    `conduit.dag.node` builds each node's ``def`` line by string formatting, so a
    name that is not a plain Python identifier fails as an opaque ``SyntaxError``
    deep in module generation (or, worse, injects statements). The generated
    module's own namespace names are reserved too: a node called ``xr`` would
    shadow the helper for every later node's expression.
    """
    from .dag.node import RESERVED_NODE_NAMES

    where = f"[[node]] '{node_name}' {field_}"
    if not isinstance(value, str) or not value.isidentifier():
        raise ValueError(
            f"{where}: {value!r} is not a valid Python identifier, and node names "
            f"and inputs become identifiers in the generated node module."
        )
    if keyword.iskeyword(value):
        raise ValueError(f"{where}: {value!r} is a Python keyword.")
    if value in RESERVED_NODE_NAMES:
        raise ValueError(
            f"{where}: {value!r} is reserved — it names a helper bound in every "
            f"generated node module ({sorted(RESERVED_NODE_NAMES)}). Choose "
            f"another name."
        )


@dataclass
class NodeSpec:
    """Specification for a single (already fan-out-expanded) [[node]] entry.

    ``units`` / ``dims`` / ``dtype`` / ``coords`` / ``freq`` declare the node's output
    contract (read by the build-time contract check and stamped/validated at runtime).
    A ``passthrough`` node instead declares *no* fixed output contract for the facets
    a passthrough preserves, and is tagged so the contract check propagates its
    input's declaration across it — the shape the ``[[resample]]`` preset generates.
    ``freq`` is the exception: a resample *changes* the frequency, so it is declared
    explicitly even on a passthrough node.
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
    freq: str | None = None
    passthrough: bool = False

    @classmethod
    def from_config(cls, entry: dict) -> "NodeSpec":
        """Construct and validate from a raw (expanded) [[node]] TOML entry."""
        name = entry.get("name")
        _assert_node_identifier(name, "name", name)
        for inp in entry.get("inputs", []):
            _assert_node_identifier(inp, "inputs", name)
        has_expression = "expression" in entry
        has_import_path = "_import_path" in entry
        has_function = "function" in entry
        if has_expression and (has_import_path or has_function):
            raise ValueError(
                f"Node entry for '{name}' must specify either "
                "'expression' or ('_import_path' + 'function'), not both."
            )
        if not has_expression and not (has_import_path or has_function):
            raise ValueError(
                f"Node entry for '{name}' must specify either "
                "'expression' or ('_import_path' + 'function')."
            )
        if has_import_path != has_function:
            missing = "function" if has_import_path else "_import_path"
            present = "_import_path" if has_import_path else "function"
            raise ValueError(
                f"Node entry for '{name}' specifies '{present}' but is missing "
                f"'{missing}'. A function node needs both keys: "
                f"'_import_path' (the module) and 'function' (the name within it)."
            )
        units = entry.get("units")
        if units is not None:
            # Fail fast on a malformed/unknown unit, at parse time.
            from xarray_annotated.units import assert_valid_unit

            assert_valid_unit(units, f"node '{name}' units")
        dtype = entry.get("dtype")
        if dtype is not None:
            # Fail fast on a malformed dtype, at parse time, via the same
            # declaration validator the schema decorator uses.
            from xarray_annotated.schema import Dtype, assert_valid_schema

            assert_valid_schema(Dtype(dtype), f"node '{name}' dtype")
        freq = entry.get("freq")
        if freq is not None:
            # Fail fast on an unparseable pandas offset alias, at parse time.
            from xarray_annotated.temporal import Freq, assert_valid_freq

            assert_valid_freq(Freq(freq), f"node '{name}' freq")
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
            freq=freq,
            passthrough=bool(entry.get("passthrough", False)),
        )


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

    Selects a contiguous slice ``[start, stop)`` of one dimension (``dim``, default
    ``pixel``) so that independent ``conduit run`` processes can each handle a
    different chunk of the same input files. ``stop`` is exclusive (Python slice
    convention).

    ``dim`` mirrors `BlockingSpec.dim`: the two mechanisms partition the same way
    and differ only in *who* runs the parts (one process sequentially vs. many
    processes concurrently), so a non-gridded pipeline can subset over ``location``
    or ``site`` just as it can block over it. The one place ``pixel`` is still
    special is the gridded Zarr store (`conduit.gridded.io.create_output_store`),
    whose layout *is* the pixel grid; it rejects any other ``dim``.
    """

    start: int
    stop: int
    dim: str = "pixel"

    @classmethod
    def from_config(cls, entry: dict) -> "SubsetSpec":
        """Construct and validate from a raw [subset] TOML entry."""

        def _index(key: str) -> int:
            value = entry.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(
                    f"[subset] {key!r} must be a non-negative integer, got {value!r}."
                )
            return value

        start = _index("start")
        stop = _index("stop")
        if stop <= start:
            raise ValueError(
                f"[subset] 'stop' ({stop}) must be greater than 'start' ({start})."
            )
        dim = entry.get("dim", "pixel")
        if not isinstance(dim, str) or not dim:
            raise ValueError(f"[subset] 'dim' must be a non-empty string, got {dim!r}.")
        return cls(start=start, stop=stop, dim=dim)


@dataclass
class IOSpec:
    """I/O specification for a single input or output section.

    ``vars`` maps this section's file variables to Hamilton node names, in one of
    three forms:

    - a **list** ``["temperature", ...]`` — the node name is derived from the file
      variable and the section's suffix (``{var}{suffix}``), the convenient default;
    - a **mapping** ``{node_name: file_var}`` — an explicit, suffix-free alias, e.g.
      ``{temperature_daily = "t2m"}`` (input: read file var ``t2m`` as node
      ``temperature_daily``) or ``{gpp_daily = "gpp"}`` (output: write node
      ``gpp_daily`` to file var ``gpp``). Use this to decouple file naming from DAG
      naming, or to alias a variable without renaming the file;
    - **omitted** (``None``) — *inputs only*: bind **every** variable in the file,
      through the suffix. An empty list is not a way to spell this and is rejected:
      binding nothing is never what a section is for.

    ``suffix`` controls the list/load-everything forms' node names. When ``None``
    (the default) the effective suffix is derived from the section label
    (``_<label>``). Set ``suffix = ""`` on any section for bare names, or
    ``suffix = "_x"`` to choose an explicit suffix. It is ignored for the mapping
    form (which is already explicit). See ``conduit.io.effective_suffix``.
    """

    path: str
    vars: list[str] | dict[str, str] | None = None
    suffix: str | None = None


def _severity(value: Any, label: str, key: str) -> str | None:
    """Validate an ``error``/``warn``/``ignore`` policy key; ``None`` passes through."""
    if value is not None and value not in ("error", "warn", "ignore"):
        raise ValueError(
            f"[{label}] {key!r} must be one of 'error', 'warn', 'ignore', "
            f"got {value!r}."
        )
    return value


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


@dataclass(frozen=True)
class AnnotationPolicySpec:
    """The [annotations] section: contract-validation policy, for every facet.

    The section's user-facing keys (``mode``, ``exact``, ``on_mismatch``,
    ``on_uninferable``) map onto xarray-annotated's three policy objects (units,
    schema, temporal); `apply` is what pushes them into that library's
    process-global policy. Every axis is ``None`` when unset, meaning "defer to the
    process-wide default".

    `apply` must be called by *every* entry point that builds a DAG — the build-time
    contract check consults the global policy, so a command that skipped it would
    accept a config that ``conduit run`` rejects.
    """

    enabled: bool | None = None
    on_missing: str | None = None
    on_inexact: str | None = None
    on_mismatch: str | None = None
    on_uninferable: str | None = None

    def apply(self) -> None:
        """Push this policy into xarray-annotated's process-global policy."""
        if self.enabled is not None:
            from xarray_annotated.units import set_policy

            set_policy(enabled=self.enabled)

        if self.on_missing is not None:
            from xarray_annotated.units import OnMissing, set_policy

            set_policy(on_missing=cast(OnMissing, self.on_missing))

        if self.on_inexact is not None:
            from xarray_annotated.units import OnInexact, set_policy

            set_policy(on_inexact=cast(OnInexact, self.on_inexact))

        # `on_mismatch` means the same thing in both validate-only domains ("the
        # array contradicts its declaration"), so one config key drives both.
        if self.on_mismatch is not None:
            from xarray_annotated.schema import OnMismatch
            from xarray_annotated.schema import set_policy as set_schema_policy
            from xarray_annotated.temporal import set_policy as set_temporal_policy

            set_schema_policy(on_mismatch=cast(OnMismatch, self.on_mismatch))
            set_temporal_policy(on_mismatch=cast(OnMismatch, self.on_mismatch))

        if self.on_uninferable is not None:
            from xarray_annotated.temporal import OnUninferable
            from xarray_annotated.temporal import set_policy as set_temporal_policy

            set_temporal_policy(on_uninferable=cast(OnUninferable, self.on_uninferable))


@dataclass
class CheckSpec:
    """One entry of ``[validation].checks``: a named input-compatibility check.

    ``check`` is a key in `conduit.checks.CHECKS`; ``inputs`` are the resolved
    ``[inputs.*]`` section labels to pass (``["*"]`` already expanded at parse
    time); ``kwargs`` are the remaining inline-table keys forwarded verbatim.
    """

    check: str
    inputs: list[str]
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedConfig:
    """Parsed pipeline configuration, ready to pass to build_driver."""

    modules: list[str]
    driver_config: dict[str, Any]
    node_specs: list["NodeSpec"] = field(default_factory=list)
    input_specs: dict[str, "IOSpec"] = field(default_factory=dict)
    output_specs: dict[str, "IOSpec"] = field(default_factory=dict)
    cache_spec: "CacheSpec | None" = None
    blocking_spec: "BlockingSpec | None" = None
    subset_spec: "SubsetSpec | None" = None
    checks: list["CheckSpec"] = field(default_factory=list)
    annotations: "AnnotationPolicySpec" = field(
        default_factory=lambda: AnnotationPolicySpec()
    )


# ---------------------------------------------------------------------------
# Fan-out / desugaring helpers ([[node]] for_each + [[resample]] preset)
# ---------------------------------------------------------------------------


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

    Each variable ``v`` becomes a node ``{v}_{target}`` that applies
    `conduit.transforms.resample` to ``{v}_{source}``; the node is a passthrough
    (unit/dim preserving), so the contract check propagates the source's declared
    contract across it.

    The one facet a resample does *not* preserve is the frequency — it is what the
    node changes — so the node declares its own: ``freq``. Every resample therefore
    carries a checkable output-frequency contract (including its anchor, so a
    fat-fingered ``W-WED`` is caught), which a downstream consumer's ``Freq``
    declaration is compared against at build time.
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
        # Lazy import breaks the config -> checks -> io -> config cycle.
        from .checks import CHECKS

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
