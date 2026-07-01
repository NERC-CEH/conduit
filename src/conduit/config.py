"""Configuration management for conduit."""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

import tomli_w

RESAMPLE_FREQ_MAP: dict[tuple[str, str], str] = {
    ("daily", "weekly"): "7D",
    ("daily", "monthly"): "1ME",
    ("weekly", "monthly"): "1ME",
    # TODO: expose frequency strings as config options to support e.g. "W" (week-ending
    # Sunday) vs "7D" (rolling 7-day), or "MS" (month-start) vs "1ME" (month-end)
}

_VALID_AGGFUNCS: frozenset[str] = frozenset(
    {"mean", "sum", "max", "min", "first", "last"}
)


@dataclass
class ResampleSpec:
    """Specification for a single [[resample]] entry."""

    vars: list[str]
    source_freq: str
    target_freq: str
    aggfunc: str = "mean"

    @property
    def freq(self) -> str:
        """Return xarray resample frequency string from source/target freq pair."""
        return RESAMPLE_FREQ_MAP[(self.source_freq, self.target_freq)]

    @classmethod
    def from_config(cls, entry: dict) -> "ResampleSpec":
        """Construct and validate from a raw [[resample]] TOML entry."""
        source_freq = entry["from_freq"]
        target_freq = entry["to_freq"]
        aggfunc = entry.get("aggfunc", "mean")
        vars_ = entry["vars"]

        if (source_freq, target_freq) not in RESAMPLE_FREQ_MAP:
            raise ValueError(
                f"Unsupported resample direction '{source_freq}' → '{target_freq}'. "
                f"Supported: {sorted(RESAMPLE_FREQ_MAP)}"
            )
        if aggfunc not in _VALID_AGGFUNCS:
            raise ValueError(
                f"Unsupported aggfunc '{aggfunc}'. Supported: {sorted(_VALID_AGGFUNCS)}"
            )

        return cls(
            vars=vars_,
            source_freq=source_freq,
            target_freq=target_freq,
            aggfunc=aggfunc,
        )


@dataclass
class NodeSpec:
    """Specification for a single [[node]] entry."""

    name: str
    inputs: list[str]
    expression: str | None
    import_path: str | None
    function: str | None
    units: str | None = None

    @classmethod
    def from_config(cls, entry: dict) -> "NodeSpec":
        """Construct and validate from a raw [[node]] TOML entry."""
        has_expression = "expression" in entry
        has_function = "_import_path" in entry or "function" in entry
        if has_expression and has_function:
            raise ValueError(
                f"Node entry for '{entry.get('name')}' must specify either "
                "'expression' or ('_import_path' + 'function'), not both."
            )
        if not has_expression and not has_function:
            raise ValueError(
                f"Node entry for '{entry.get('name')}' must specify either "
                "'expression' or ('_import_path' + 'function')."
            )
        units = entry.get("units")
        if units is not None:
            # Fail fast on a malformed/unknown unit, at parse time.
            from .units import assert_valid_unit

            assert_valid_unit(units, f"node '{entry.get('name')}' units")
        return cls(
            name=entry["name"],
            inputs=entry["inputs"],
            expression=entry.get("expression"),
            import_path=entry.get("_import_path"),
            function=entry.get("function"),
            units=units,
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

    ``suffix`` controls how this section's variables are mapped to Hamilton node
    names. When ``None`` (the default) the effective suffix is derived from the
    section label: ``_<label>`` for a temporal/grouped section, or ``""`` (bare
    names) for the conventional ``static`` label. Set ``suffix = ""`` on any
    section for bare names, or ``suffix = "_x"`` to choose an explicit suffix.
    See ``conduit.io.effective_suffix``.
    """

    path: str
    vars: list[str]
    suffix: str | None = None


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
    units_mode: str | None = None
    units_exact: bool | None = None


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
                vars=params.get("vars") or [],
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
                vars=vars_,
                suffix=params.get("suffix"),
            )

    def _parse_resample(self, data: dict, driver_config: dict) -> list[str]:
        """Handle [[resample]] section."""
        seen_outputs: set[str] = set()
        specs: list[ResampleSpec] = []
        for entry in data.pop("resample", []):
            spec = ResampleSpec.from_config(entry)
            for var in spec.vars:
                out = f"{var}_{spec.target_freq}"
                if out in seen_outputs:
                    raise ValueError(
                        f"Duplicate resample output '{out}' in [[resample]]"
                    )
                seen_outputs.add(out)
            specs.append(spec)
        if specs:
            driver_config["resample_specs"] = specs
            return ["resample"]
        return []

    def _parse_node(self, data: dict, driver_config: dict) -> list[str]:
        """Handle [[node]] section."""
        seen_names: set[str] = set()
        specs: list[NodeSpec] = []
        for entry in data.pop("node", []):
            spec = NodeSpec.from_config(entry)
            if spec.name in seen_names:
                raise ValueError(f"Duplicate node name '{spec.name}' in [[node]]")
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

    def _parse_units(self, data: dict) -> tuple[str | None, bool | None]:
        """Handle the [units] section.

        Returns ``(mode, exact)``: the validation mode string (or ``None``) and
        the exact-unit-match flag for the build-time check (or ``None`` when not
        given). Both are ``None`` if there is no [units] section.
        """
        entry = data.pop("units", None)
        if entry is None:
            return None, None
        mode = entry.get("mode")
        if mode is not None and mode not in ("strict", "warn", "off"):
            raise ValueError(
                f"[units] 'mode' must be one of 'strict', 'warn', 'off', got {mode!r}."
            )
        exact = entry.get("exact")
        if exact is not None and not isinstance(exact, bool):
            raise ValueError(f"[units] 'exact' must be a boolean, got {exact!r}.")
        return mode, exact

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
        - [[node]]        — config-driven custom nodes
        - [[resample]]    — temporal resampling module
        - [cache]         — Hamilton result caching (path, recompute, disable)
        - [blocking]      — pixel-blocked execution (block_size)
        - [subset]        — spatial pixel slice (pixel_start, pixel_end)
        - [units]         — unit validation mode ('strict', 'warn', 'off')

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
        modules += self._parse_node(data, driver_config)
        modules += self._parse_resample(data, driver_config)
        cache_spec = self._parse_cache(data)
        blocking_spec = self._parse_blocking(data)
        subset_spec = self._parse_subset(data)
        units_mode, units_exact = self._parse_units(data)
        modules += self._parse_external_modules(data, driver_config)
        return ParsedConfig(
            modules=modules,
            driver_config=driver_config,
            input_specs=input_specs,
            output_specs=output_specs,
            cache_spec=cache_spec,
            blocking_spec=blocking_spec,
            subset_spec=subset_spec,
            units_mode=units_mode,
            units_exact=units_exact,
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
