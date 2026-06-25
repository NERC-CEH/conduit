"""Runtime unit validation helpers for the SatTerC DAG.

Each model node owns its own unit declarations via the
`satterc.dag._utils.declare_units` decorator (``input_units`` / ``output_units``);
there is deliberately no central registry of variable units, so the framework
never has to anticipate what inputs a user might bring. This module provides the
validation/conversion helpers and the validation-mode state used by that decorator.

Only ``DataArray`` inputs/outputs carry units and are validated/stamped. Other
node arguments (``DatetimeIndex``, scalar ``float``/``int``/``str`` config
parameters) have no attached unit metadata at runtime, so there is nothing to
validate or convert and they are left untouched.

Importing this module configures ``pint-xarray`` to use the UDUNITS-aware pint
registry shipped by ``cf-xarray``. That registry parses CF-convention unit
strings such as ``"umol m-2 s-1"`` and ``"g m-2 d-1"`` (which the plain pint
registry cannot), so declared units and ``units`` attributes read from CF
NetCDF/Zarr files are interpreted consistently.

Units are declared in canonical UDUNITS style (e.g. ``"umol m-2 s-1"``, not
``"µmol/m²/s"``) to match CF attributes on disk.
"""

import os
import types
import warnings
from contextlib import contextmanager
from typing import (
    Annotated,
    Any,
    Literal,
    Union,
    get_args,
    get_origin,
    get_type_hints,
    is_typeddict,
)

import cf_xarray.units  # noqa: F401 -- registers the UDUNITS-aware pint registry
import pint
import pint_xarray
import xarray as xr
from cf_xarray.units import units as _UREG
from pint_xarray.errors import PintExceptionGroup

# Point pint-xarray's accessor at the cf-xarray (UDUNITS) registry, once, on
# import. Every ``.pint.quantify()`` call below then understands CF unit strings.
pint_xarray.setup_registry(_UREG)


class UnitsWarning(UserWarning):
    """Emitted when a DataArray input cannot be fully unit-validated.

    Raised by `check_units` (and therefore by `declare_units`-decorated nodes)
    when an input has a missing or unparseable ``units`` attribute and the active
    validation mode is ``"warn"``. Also raised by the static DAG unit check when
    it finds a unit declaration mismatch.

    Subclasses ``UserWarning`` so callers can target it specifically::

        import warnings
        from satterc import UnitsWarning
        warnings.filterwarnings("error", category=UnitsWarning)
    """


Mode = Literal["strict", "warn", "off"]

VALID_MODES: frozenset[str] = frozenset({"strict", "warn", "off"})

#: Validation mode used when none is set via config/env. ``warn`` flags missing
#: ``units`` attributes without failing, which suits development and keeps the
#: feature non-breaking for inputs that lack CF metadata.
DEFAULT_MODE: Mode = "warn"

#: Environment variable that overrides the configured/default mode.
MODE_ENV_VAR = "SATTERC_UNITS_MODE"

#: Default for the build-time *exact-unit-match* check. When ``False`` the static
#: check only flags dimensionally incompatible edges; when ``True`` it also flags
#: dimensionally compatible but non-identical unit strings (e.g. ``"Pa"`` vs
#: ``"hPa"``). Off by default, since the framework auto-converts compatible units.
DEFAULT_EXACT: bool = False

#: Environment variable that overrides the configured/default exact-match flag.
EXACT_ENV_VAR = "SATTERC_UNITS_EXACT"

#: String values (lower-cased) accepted for the exact-match environment variable.
_TRUTHY: frozenset[str] = frozenset({"1", "true", "yes", "on"})
_FALSEY: frozenset[str] = frozenset({"0", "false", "no", "off"})

_process_mode: Mode | None = None
_process_exact: bool | None = None


# ---------------------------------------------------------------------------
# Mode handling
# ---------------------------------------------------------------------------


def _validate_mode(mode: str) -> Mode:
    if mode not in VALID_MODES:
        raise ValueError(
            f"Invalid units mode {mode!r}. Choose one of {sorted(VALID_MODES)}."
        )
    return mode  # type: ignore[return-value]


def set_mode(mode: str | None) -> None:
    """Set the process-wide unit validation mode.

    Passing ``None`` clears the process override so the default (or the
    ``SATTERC_UNITS_MODE`` environment variable) applies.
    """
    global _process_mode
    _process_mode = None if mode is None else _validate_mode(mode)


def get_mode() -> Mode:
    """Resolve the active unit validation mode.

    Resolution order: ``SATTERC_UNITS_MODE`` environment variable, then the
    value set via `set_mode`, then `DEFAULT_MODE`.
    """
    env = os.environ.get(MODE_ENV_VAR)
    if env:
        return _validate_mode(env.lower())
    if _process_mode is not None:
        return _process_mode
    return DEFAULT_MODE


@contextmanager
def mode(mode: str | None):
    """Temporarily override the unit validation mode.

    Restores the previous mode on exit, even if an exception is raised.

    >>> with units.mode("strict"):
    ...     check_units(da, "Pa", "vpd", get_mode())
    """
    global _process_mode
    old = _process_mode
    set_mode(mode)
    try:
        yield
    finally:
        _process_mode = old


def set_exact_match(exact: bool | None) -> None:
    """Set the process-wide exact-unit-match flag for the build-time check.

    Passing ``None`` clears the process override so the default (or the
    ``SATTERC_UNITS_EXACT`` environment variable) applies.
    """
    global _process_exact
    _process_exact = None if exact is None else bool(exact)


def get_exact_match() -> bool:
    """Resolve the active exact-unit-match flag.

    Resolution order: ``SATTERC_UNITS_EXACT`` environment variable, then the
    value set via `set_exact_match`, then `DEFAULT_EXACT`.
    """
    env = os.environ.get(EXACT_ENV_VAR)
    if env:
        lowered = env.lower()
        if lowered in _TRUTHY:
            return True
        if lowered in _FALSEY:
            return False
        raise ValueError(
            f"Invalid {EXACT_ENV_VAR} value {env!r}. "
            f"Use one of {sorted(_TRUTHY | _FALSEY)}."
        )
    if _process_exact is not None:
        return _process_exact
    return DEFAULT_EXACT


# ---------------------------------------------------------------------------
# Unit resolution & checking
# ---------------------------------------------------------------------------


def assert_valid_unit(unit: str, context: str) -> None:
    """Raise ``ValueError`` if ``unit`` is not parseable by the registry.

    Used to fail fast at decoration/import time: a malformed or undefined unit
    string (a typo such as ``"degrees_C"``, or ``"not_a_unit"``) is rejected as
    soon as a node is defined, rather than only when that node runs in
    ``strict``/``warn`` mode — and never in ``off`` mode. ``context`` names the
    offending site (e.g. ``"pmodel input 'vpd_weekly'"``) for the message.

    The registry raises a variety of exception types for bad input
    (``pint.UndefinedUnitError``, ``AssertionError``, …); all are caught and
    re-raised as a single, clear ``ValueError``.
    """
    try:
        _UREG.Unit(unit)
    except Exception as exc:
        # The registry raises several error types for bad input; normalise them.
        raise ValueError(
            f"{context}: declared unit {unit!r} is not a recognised "
            f"UDUNITS/pint unit ({type(exc).__name__}: {exc})"
        ) from exc


def units_compatible(a: str, b: str) -> bool:
    """Return whether two declared units are *dimensionally* compatible.

    Mirrors the runtime conversion semantics of `check_units`: ``"hPa"`` and
    ``"Pa"`` are compatible (one converts to the other), whereas ``"Pa"`` and
    ``"kg"`` are not. Used by the build-time DAG check
    (`satterc.dag.unit_check.check_dag_units`). Both strings are assumed
    already validated by `assert_valid_unit` at decoration time.
    """
    return _UREG.Unit(a).is_compatible_with(_UREG.Unit(b))


def units_equal(a: str, b: str) -> bool:
    """Return whether two units are the *same* unit (no conversion needed).

    Compares the parsed units, so different spellings of the same unit are equal
    (``"Pa"`` == ``"pascal"``, ``"1"`` == ``"dimensionless"``) while a prefixed
    unit differs (``"hPa"`` != ``"Pa"``). This is the notion of *exact* used by
    both the build-time check and the runtime ``exact`` mode: "exact" forbids any
    value-changing conversion but tolerates equivalent spellings.
    """
    return _UREG.Unit(a) == _UREG.Unit(b)


def unwrap_annotated(hint: Any) -> Any:
    """Return the underlying type of an ``Annotated`` hint, else the hint itself.

    ``Annotated[DataArray, "degC"]`` → ``DataArray``; a non-``Annotated`` hint is
    returned unchanged. Lets type comparisons (e.g. ``t is DataArray``) see through
    the unit metadata that signature-native declarations attach to node parameters.
    """
    return get_args(hint)[0] if get_origin(hint) is Annotated else hint


def _is_dataarray_type(tp: Any) -> bool:
    """Return whether ``tp`` is ``DataArray`` (possibly wrapped in a Union).

    Accepts a bare ``DataArray`` as well as ``DataArray | None`` /
    ``Optional[DataArray]`` (and any other union that includes ``DataArray``), so
    an optional DataArray parameter can still carry a declared unit. Anything
    else (scalars, ``str``, ``bool``, ``Dataset``, ``DatetimeIndex``, …) is not a
    unit-bearing type.
    """
    if tp is xr.DataArray:
        return True
    if get_origin(tp) in (Union, types.UnionType):
        return any(_is_dataarray_type(arg) for arg in get_args(tp))
    return False


def annotated_unit(hint: Any) -> str | None:
    """Return the declared unit carried by an ``Annotated`` type hint, or ``None``.

    The unit is the **first ``str``** in the ``Annotated`` metadata, e.g.
    ``Annotated[DataArray, "degC"]`` → ``"degC"``. This makes the metadata
    extensible: a unit may be followed by free-form annotations (a description,
    typed markers, …) that are ignored here, so

        ``Annotated[DataArray, "m s-1", "z component of velocity"]`` → ``"m s-1"``

    The convention is therefore *unit first*: the unit must precede any
    descriptive string. A description placed before the unit would be mis-read as
    the unit — but `assert_valid_unit` rejects it at decoration time unless
    the description itself parses as a valid unit, so the failure is loud.
    Non-string metadata (ints, markers) is skipped regardless of position.

    The metadata is only interpreted as a unit when the annotated base type is a
    ``DataArray`` (the only type that carries units); a descriptive string on a
    non-``DataArray`` parameter (e.g. ``Annotated[bool, "toggles X"]``) is *not* a
    unit and yields ``None``. Non-``Annotated`` hints, or ``Annotated`` hints
    whose metadata holds no string, also return ``None``.
    """
    if get_origin(hint) is not Annotated:
        return None
    # get_args(Annotated[T, m1, m2, ...]) == (T, m1, m2, ...); skip the base type.
    args = get_args(hint)
    if not _is_dataarray_type(args[0]):
        return None
    for meta in args[1:]:
        if isinstance(meta, str):
            return meta
    return None


def units_from_signature(
    func: object,
) -> tuple[dict[str, str], dict[str, str] | str | None]:
    """Extract declared units from a node function's type annotations.

    Reads ``get_type_hints(func, include_extras=True)`` and interprets
    ``Annotated[..., "<unit>"]`` metadata as unit declarations:

    - **inputs**: every parameter whose hint is ``Annotated`` with a string unit
      contributes to the returned ``input_units`` mapping (others are ignored);
    - **output**: if the return hint is a ``TypedDict``, each field name maps to
      its ``Annotated`` unit (a ``dict``); if it is a bare ``Annotated[DataArray,
      unit]`` return, the bare unit ``str``; otherwise ``None``.

    This is the single source the runtime `satterc.dag._utils.declare_units`
    decorator and the (Phase 2) static DAG check both read, so unit declarations
    live in one place — the node's own signature.
    """
    hints = get_type_hints(func, include_extras=True)
    ret = hints.pop("return", None)

    input_units = {
        name: unit
        for name, hint in hints.items()
        if (unit := annotated_unit(hint)) is not None
    }

    output_units: dict[str, str] | str | None
    if is_typeddict(ret):
        ret_hints = get_type_hints(ret, include_extras=True)
        output_units = {
            name: unit
            for name, hint in ret_hints.items()
            if (unit := annotated_unit(hint)) is not None
        }
    else:
        output_units = annotated_unit(ret)

    return input_units, output_units


def check_units(
    da: xr.DataArray,
    declared: str,
    name: str,
    mode: Mode,
    exact: bool = False,
    qualname: str | None = None,
) -> xr.DataArray:
    """Validate and convert an input ``DataArray`` to its declared unit.

    Returns a ``DataArray`` whose data is expressed in ``declared`` and whose
    ``units`` attribute equals ``declared``. If the input carries no ``units``
    attribute, or one the registry cannot parse (e.g. a non-CF string like
    ``"fraction"``), it cannot be validated and behaviour follows ``mode``
    (``strict`` raises, ``warn`` warns and returns the array unchanged, ``off``
    returns unchanged). A dimensional incompatibility between two *parseable* units
    raises ``pint.DimensionalityError`` regardless of mode.

    When ``exact`` is ``True``, an input whose unit is dimensionally compatible
    with ``declared`` but is *not the same unit* (i.e. conversion would change the
    values, e.g. ``"hPa"`` where ``"Pa"`` is declared) raises ``ValueError``
    instead of being silently converted. Equivalent spellings (``"pascal"`` for
    ``"Pa"``) are still accepted, since no value change is implied.

    ``qualname`` is the ``__qualname__`` of the calling node function; when
    provided it is prepended to warning messages as ``[qualname] ...`` so the
    source of the warning is identifiable without inspecting the call stack.
    """
    prefix = f"[{qualname}] " if qualname else ""
    have = da.attrs.get("units")
    if have is None:
        if mode == "strict":
            raise ValueError(
                f"{prefix}input {name!r} has no 'units' attribute "
                f"(declared {declared!r})"
            )
        if mode == "warn":
            warnings.warn(
                f"{prefix}input {name!r} unvalidated: no 'units' attribute "
                f"(declared {declared!r})",
                UnitsWarning,
                stacklevel=2,
            )
        return da
    try:
        _UREG.Unit(have)
    except Exception as exc:
        # A units attribute that exists but the registry cannot parse can no more be
        # validated than a missing one; route it through the same mode policy rather
        # than letting an opaque parse error escape (and break a ``warn`` run).
        if mode == "strict":
            raise ValueError(
                f"{prefix}input {name!r} has unparseable 'units' attribute {have!r} "
                f"(declared {declared!r}): {type(exc).__name__}: {exc}"
            ) from exc
        if mode == "warn":
            warnings.warn(
                f"{prefix}input {name!r} unvalidated: unparseable 'units' attribute "
                f"{have!r} (declared {declared!r})",
                UnitsWarning,
                stacklevel=2,
            )
        return da
    if exact and units_compatible(have, declared) and not units_equal(have, declared):
        raise ValueError(
            f"input {name!r}: unit {have!r} differs from declared {declared!r} "
            f"and exact unit matching is enabled (no implicit conversion)"
        )
    try:
        converted = da.pint.quantify().pint.to(declared).pint.dequantify()
    except PintExceptionGroup as group:
        # pint-xarray wraps conversion failures in an ExceptionGroup; surface the
        # underlying DimensionalityError directly for a clean, catchable error.
        dim_errors = [
            exc for exc in group.exceptions if isinstance(exc, pint.DimensionalityError)
        ]
        if dim_errors:
            err = dim_errors[0]
            err.add_note(f"while validating input {name!r}")
            raise err from None
        raise
    # dequantify writes pint's canonical unit name (e.g. 'pascal'); restore the
    # declared UDUNITS string so downstream re-parsing uses our spelling.
    converted.attrs["units"] = declared
    return converted
