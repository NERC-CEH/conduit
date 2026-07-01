import functools
import inspect
from collections.abc import Callable
from typing import Any

import xarray as xr

from ..units import (
    assert_valid_unit,
    check_units,
    get_exact_match,
    get_mode,
    units_from_signature,
)


def declare_units(func: Callable[..., Any]) -> Callable[..., Any]:
    """Apply a node's signature-declared units at runtime.

    Reads the decorated node's own type annotations once, via
    `conduit.units.units_from_signature`: parameters annotated
    ``Annotated[DataArray, "<unit>"]` declare input units, and a ``TypedDict``
    return (or a bare ``Annotated[DataArray, "<unit>"]`` return) declares output
    units. Those annotations are the single source of truth — the same one the
    (Phase 2) static DAG check reads off the Hamilton node — so units are never
    duplicated.

    At call time the wrapper:

    1. validates/converts each declared ``DataArray`` input to its unit via
       `conduit.units.check_units`, honouring the active mode
       (`conduit.units.get_mode`); validation is skipped entirely in ``off`` mode;
    2. runs the node body;
    3. stamps each declared output ``DataArray`` with its unit (a ``dict`` return
       is stamped per output name; a single ``DataArray`` return is stamped with
       the bare declared unit).

    Only ``DataArray`` values are validated/stamped. Non-``DataArray`` arguments
    (`DatetimeIndex`, `Dataset`, scalar config parameters) carry no unit metadata
    and pass through untouched. This decorator does **not** convert between
    ``DataArray`` and ``ndarray`` — that boundary is the `xarray.apply_ufunc`
    seam inside each model node's inner numpy implementation.

    Every declared unit string is checked against the registry **here, at
    decoration time**, so a malformed or undefined unit (a typo) fails fast at
    import — regardless of the active mode — rather than only when the node runs.
    """
    input_units, output_units = units_from_signature(func)
    sig = inspect.signature(func)

    # Fail fast on unparseable declarations (independent of validation mode).
    qualname = getattr(func, "__qualname__", repr(func))
    for name, unit in input_units.items():
        assert_valid_unit(unit, f"{qualname} input {name!r}")
    if isinstance(output_units, str):
        assert_valid_unit(output_units, f"{qualname} output")
    elif isinstance(output_units, dict):
        for name, unit in output_units.items():
            assert_valid_unit(unit, f"{qualname} output {name!r}")

    def _stamp(result: Any) -> Any:
        if isinstance(output_units, str):
            if isinstance(result, xr.DataArray):
                result.attrs["units"] = output_units
        elif isinstance(output_units, dict) and isinstance(result, dict):
            for name, value in result.items():
                declared = output_units.get(name)
                if declared is not None and isinstance(value, xr.DataArray):
                    value.attrs["units"] = declared
        return result

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        mode = get_mode()
        if mode != "off" and input_units:
            exact = get_exact_match()
            bound = sig.bind_partial(*args, **kwargs)
            for name, val in list(bound.arguments.items()):
                declared = input_units.get(name)
                if declared is not None and isinstance(val, xr.DataArray):
                    bound.arguments[name] = check_units(
                        val, declared, name, mode, exact, qualname=qualname
                    )
            args, kwargs = bound.args, bound.kwargs

        return _stamp(func(*args, **kwargs))

    return wrapper
