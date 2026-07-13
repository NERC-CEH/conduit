"""The parsed configuration data model: one dataclass per config section.

A **leaf** module: it imports nothing else from conduit. That is deliberate. These
specs are what `conduit.io`, `conduit.checks` and `conduit.dag` all need to talk
about, and while they lived in `config.py` — alongside the TOML parser, which needs
`checks` to validate check names — every one of those modules had to import
`config` lazily to dodge a `config -> checks -> io -> config` cycle. Keeping the
data model separate from the parser removes the cycle rather than working around it.

Each spec validates itself in `from_config`, so a malformed section fails at parse
time with a message naming the section — never later, inside a DAG node.
"""

import keyword
from dataclasses import dataclass, field
from typing import Any, cast

_VALID_AGGFUNCS: frozenset[str] = frozenset(
    {"mean", "sum", "max", "min", "first", "last"}
)


# ---------------------------------------------------------------------------
# Spec dataclasses (the parsed data model)
# ---------------------------------------------------------------------------


@dataclass
class ResampleSpec:
    """Specification for a single [[resample]] entry.

    ``source`` and ``target`` (TOML ``from`` / ``to``) are **node-name suffixes**, not
    frequencies: ``from = "daily"`` reads ``{var}_daily``, ``to = "weekly"`` writes
    ``{var}_weekly``, and nothing is inferred from either (see `conduit.io.load_inputs`
    on inert labels). ``freq`` alone says what happens to the time axis.

    Desugared to fan-out passthrough nodes by
    `conduit.config.resample_to_node_entry`.
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
    contract: validated and stamped at runtime, and read by the build-time check.
    ``passthrough`` instead declares no fixed contract and tags the node so the check
    propagates its input's declaration across it — per facet, so ``freq`` may still be
    declared. See `conduit.dag.contract_check` for what propagation means.
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
