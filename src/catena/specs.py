"""The parsed configuration data model: one dataclass per config section.

`catena.config` builds these from a TOML file; `run`, `dry_run` and
`build_graph` accept the resulting `ParsedConfig` in place of a path.

Each spec validates itself in `from_config`, so a malformed section fails at parse
time with a message naming the section, never later inside a DAG node.
"""

import keyword
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

from .errors import CatenaValueError

_VALID_AGGFUNCS: frozenset[str] = frozenset(
    {"mean", "sum", "max", "min", "first", "last"}
)

#: Node names and node inputs a config may not use. Each one names a helper bound
#: in every generated node module's namespace, so a node called ``xr`` would shadow
#: that helper for every later node's expression. `catena.nodegen` binds them and
#: `NodeSpec.from_config` rejects them at parse time; the two are kept in step by
#: ``test_nodegen.py::test_reserved_names_match_generated_namespace``.
RESERVED_NODE_NAMES: frozenset[str] = frozenset(
    {"xr", "xra", "Any", "__import_module", "__transforms"}
)

#: Top-level config sections and keys catena parses itself. A section named here is
#: never treated as a user module, so a package registering one of these names would
#: register something no config could ever reach.
RECOGNISED_SECTIONS: frozenset[str] = frozenset(
    {
        "inputs",
        "outputs",
        "validation",
        "node",
        "resample",
        "cache",
        "blocking",
        "subset",
    }
)


# ---------------------------------------------------------------------------
# Spec dataclasses (the parsed data model)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegisteredModule:
    """A config section resolved to a module by an installed package.

    Produced when a section carries no ``_import_path`` and its name matches one an
    installed package declares in the ``catena.modules`` entry-point group (see
    `catena.importing`). `run` and `dry_run` report these, so a section whose code
    comes from somewhere the config does not name is still visible.
    """

    #: The config section that named it.
    section: str
    #: The dotted module path the package registered.
    import_path: str
    #: The distribution that registered it.
    distribution: str


@dataclass
class ResampleSpec:
    """Specification for a single [[resample]] entry.

    ``source`` and ``target`` (TOML ``from`` / ``to``) are **node-name suffixes**, not
    frequencies: ``from = "daily"`` reads ``{var}_daily``, ``to = "weekly"`` writes
    ``{var}_weekly``, and nothing is inferred from either (see `catena.io.load_inputs`
    on inert labels). ``freq`` alone says what happens to the time axis.

    Desugared to fan-out passthrough nodes by
    `catena.config.resample_to_node_entry`.
    """

    vars: list[str]
    source: str
    target: str
    freq: str
    aggfunc: str = "mean"

    @classmethod
    def from_config(cls, entry: dict) -> Self:
        """Construct and validate from a raw [[resample]] TOML entry."""
        aggfunc = entry.get("aggfunc", "mean")
        if aggfunc not in _VALID_AGGFUNCS:
            raise CatenaValueError(
                f"Unsupported aggfunc '{aggfunc}'. Supported: {sorted(_VALID_AGGFUNCS)}"
            )
        missing = [key for key in ("vars", "from", "to", "freq") if key not in entry]
        if missing:
            raise CatenaValueError(
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

    `catena.nodegen` builds each node's ``def`` line by string formatting, so a
    name that is not a plain Python identifier fails as an opaque ``SyntaxError``
    deep in module generation (or, worse, injects statements). The generated
    module's own namespace names are reserved too: a node called ``xr`` would
    shadow the helper for every later node's expression.
    """
    where = f"[[node]] '{node_name}' {field_}"
    if not isinstance(value, str) or not value.isidentifier():
        raise CatenaValueError(
            f"{where}: {value!r} is not a valid Python identifier, and node names "
            f"and inputs become identifiers in the generated node module."
        )
    if keyword.iskeyword(value):
        raise CatenaValueError(f"{where}: {value!r} is a Python keyword.")
    if value in RESERVED_NODE_NAMES:
        raise CatenaValueError(
            f"{where}: {value!r} is reserved — it names a helper bound in every "
            f"generated node module ({sorted(RESERVED_NODE_NAMES)}). Choose "
            f"another name."
        )


@dataclass
class NodeSpec:
    """Specification for a single (already fan-out-expanded) [[node]] entry.

    ``units`` / ``dims`` / ``dtype`` / ``coords`` / ``freq`` declare the node's output
    contract: validated at runtime, and read by the build-time check. The output must
    already carry the declared unit, so an ``expression`` that changes it ends with
    ``.assign_attrs(units=...)``.
    ``passthrough`` instead declares no fixed contract and tags the node so the check
    propagates its input's declaration across it — per facet, so ``freq`` may still be
    declared. See `catena.contract_check` for what propagation means.
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
    def from_config(cls, entry: dict) -> Self:
        """Construct and validate from a raw (expanded) [[node]] TOML entry."""
        name = entry.get("name")
        _assert_node_identifier(name, "name", name)
        for inp in entry.get("inputs", []):
            _assert_node_identifier(inp, "inputs", name)
        has_expression = "expression" in entry
        has_import_path = "_import_path" in entry
        has_function = "function" in entry
        if has_expression and (has_import_path or has_function):
            raise CatenaValueError(
                f"Node entry for '{name}' must specify either "
                "'expression' or ('_import_path' + 'function'), not both."
            )
        if not has_expression and not (has_import_path or has_function):
            raise CatenaValueError(
                f"Node entry for '{name}' must specify either "
                "'expression' or ('_import_path' + 'function')."
            )
        if has_import_path != has_function:
            missing = "function" if has_import_path else "_import_path"
            present = "_import_path" if has_import_path else "function"
            raise CatenaValueError(
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

    path: str = ".catena_cache"
    recompute: bool | list[str] = field(default_factory=list)
    disable: bool | list[str] = field(default_factory=list)

    @classmethod
    def from_config(cls, entry: dict) -> Self:
        """Construct and validate from a raw [cache] TOML entry."""

        def _coerce(key: str) -> bool | list[str]:
            val = entry.get(key, [])
            if isinstance(val, bool):
                return val
            if isinstance(val, list) and all(isinstance(v, str) for v in val):
                return val
            raise CatenaValueError(
                f"[cache] '{key}' must be a boolean or a list of node names, "
                f"got {val!r}."
            )

        return cls(
            path=entry.get("path", ".catena_cache"),
            recompute=_coerce("recompute"),
            disable=_coerce("disable"),
        )


def assert_dim_name(value: Any, where: str) -> str:
    """Validate a required dimension-name key (``[blocking].dim``, ``[subset].dim``)."""
    if not isinstance(value, str) or not value:
        raise CatenaValueError(f"{where} must be a non-empty string, got {value!r}.")
    return value


@dataclass
class BlockingSpec:
    """Specification for the [blocking] section.

    Controls how a partition dimension (``dim``) is split into fixed-size
    sequential blocks to bound peak memory usage. ``dim`` may be any dimension:
    ``pixel`` for gridded data, or ``location``, say, for non-gridded pipelines.
    """

    block_size: int
    dim: str

    @classmethod
    def from_config(cls, entry: dict) -> Self:
        """Construct and validate from a raw [blocking] TOML entry."""
        block_size = entry.get("block_size")
        if not isinstance(block_size, int) or block_size < 1:
            raise CatenaValueError(
                "[blocking] 'block_size' must be a positive integer, "
                f"got {block_size!r}."
            )
        dim = assert_dim_name(entry.get("dim"), "[blocking] 'dim'")
        return cls(block_size=block_size, dim=dim)


@dataclass
class SubsetSpec:
    """Specification for the [subset] section.

    Selects a contiguous slice ``[start, stop)`` of one dimension (``dim``) so that
    independent ``catena run`` processes can each handle a different chunk of the same
    input files. ``stop`` is exclusive (Python slice convention).

    ``dim`` mirrors `BlockingSpec.dim`: the two mechanisms partition the same way
    and differ only in *who* runs the parts (one process sequentially vs. many
    processes concurrently), so a non-gridded pipeline can subset over ``location``
    or ``site`` just as it can block over it. The one place ``pixel`` is still
    special is the gridded Zarr store (`catena.gridded.io.create_output_store`),
    whose layout *is* the pixel grid; it rejects any other ``dim``.
    """

    start: int
    stop: int
    dim: str

    @classmethod
    def from_config(cls, entry: dict) -> Self:
        """Construct and validate from a raw [subset] TOML entry."""

        def _index(key: str) -> int:
            value = entry.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise CatenaValueError(
                    f"[subset] {key!r} must be a non-negative integer, got {value!r}."
                )
            return value

        start = _index("start")
        stop = _index("stop")
        if stop <= start:
            raise CatenaValueError(
                f"[subset] 'stop' ({stop}) must be greater than 'start' ({start})."
            )
        dim = assert_dim_name(entry.get("dim"), "[subset] 'dim'")
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
      through the suffix. An empty list is rejected:
      binding nothing is never what a section is for.

    ``suffix`` controls the list/load-everything forms' node names. When ``None``
    (the default) the effective suffix is derived from the section label
    (``_<label>``). Set ``suffix = ""`` on any section for bare names, or
    ``suffix = "_x"`` to choose an explicit suffix. It is ignored for the mapping
    form (which is already explicit). See ``catena.io.effective_suffix``.
    """

    path: str
    vars: list[str] | dict[str, str] | None = None
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
            raise CatenaValueError(
                f"[{label}] 'vars' mapping must be {{node_name = file_var}} with "
                f"string keys and values, got offending entries {bad!r}."
            )
        return dict(vars_)
    if isinstance(vars_, list) and all(isinstance(v, str) for v in vars_):
        return list(vars_)
    raise CatenaValueError(
        f"[{label}] 'vars' must be a list of names or a {{node_name = file_var}} "
        f"mapping, got {vars_!r}."
    )


@dataclass
class CheckSpec:
    """One entry of ``[validation].checks``: a named input-compatibility check.

    ``check`` is a key in `catena.input_checks.CHECKS`; ``inputs`` are the resolved
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
    #: The directory relative paths in the config resolve against, normally the
    #: one holding the config file. ``None`` for a config with no file, which can
    #: then only use absolute paths and dotted ``_import_path`` names.
    base: Path | None = None
    #: Sections whose module came from an installed package rather than an
    #: ``_import_path``, in config order.
    registered_modules: list["RegisteredModule"] = field(default_factory=list)
