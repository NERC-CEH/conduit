"""Generate Hamilton-compatible node modules from config specs."""

import sys
import types
import uuid
from importlib import import_module
from typing import TYPE_CHECKING, Any

import xarray as xr
from hamilton.function_modifiers import tag
from xarray_annotated import annotate
from xarray_annotated.schema import declare_schema
from xarray_annotated.units import declare_units

if TYPE_CHECKING:
    from conduit.config import NodeSpec

#: Hamilton tag marking a node whose output preserves its input's declared
#: contract (units/dims/dtype). The contract check reads this to propagate a
#: declaration across the node instead of requiring a fixed one. See
#: `conduit.dag.contract_check`.
PASSTHROUGH_TAG = "conduit_passthrough"


def make_node_module(node_specs: list["NodeSpec"]) -> types.ModuleType:
    """Generate a Hamilton-compatible module with one function per node spec.

    The node's *body* is built by ``exec`` (a ``[[node]]`` expression is arbitrary
    user code), but its declared output contract is attached programmatically:
    ``xarray_annotated.annotate`` builds the ``Annotated`` return hint from the raw
    spec values, then ``declare_units`` / ``declare_schema`` are applied as ordinary
    decorators — no annotation/decorator source is generated.
    """
    mod = types.ModuleType(f"conduit_node_generated_{uuid.uuid4().hex[:8]}")
    ns: dict = {
        "xr": xr,
        "Any": Any,
        "import_module": import_module,
        # Available to node expressions (e.g. the [[resample]] preset desugars to
        # ``__transforms.resample(...)``).
        "__transforms": import_module("conduit.transforms"),
    }
    for spec in node_specs:
        exec(_build_fn_code(spec), ns)
        fn = _decorate(ns[spec.name], spec)
        fn.__module__ = mod.__name__
        setattr(mod, spec.name, fn)
    sys.modules[mod.__name__] = mod
    return mod


def _decorate(fn: Any, spec: "NodeSpec") -> Any:
    """Attach the node's declared output contract to the bare ``exec``'d function."""
    # A passthrough node preserves its input's contract, so it declares none of its
    # own; it is tagged so the contract check propagates the declaration across it
    # (the shape the [[resample]] preset generates).
    if spec.passthrough:
        fn.__annotations__["return"] = annotate()
        return tag(**{PASSTHROUGH_TAG: "true"})(fn)  # type: ignore[reportArgumentType]

    # Otherwise a declared unit/dims/dtype/coords makes the node a typed producer:
    # validated/stamped at runtime (@declare_units / @declare_schema) and read by
    # the build-time contract check. Without any, it is an unchecked pass-through.
    fn.__annotations__["return"] = annotate(
        unit=spec.units,
        dims=spec.dims or None,
        dtype=spec.dtype,
        coords=spec.coords or None,
    )
    # Apply schema first, then units, so the composition is
    # ``declare_units(declare_schema(fn))`` (declare_units outermost).
    if spec.dims or spec.dtype or spec.coords:
        fn = declare_schema(fn)
    if spec.units is not None:
        fn = declare_units(fn)
    return fn


def _build_fn_code(spec: "NodeSpec") -> str:
    """Return source for the bare node function (params + body, no decorators)."""
    params = ", ".join(f"{inp}: Any" for inp in spec.inputs)
    if spec.expression is not None:
        body = f"    return {spec.expression}"
    else:
        kwargs = ", ".join(f"{inp}={inp}" for inp in spec.inputs)
        body = (
            f"    _fn = getattr(import_module({spec.import_path!r}), "
            f"{spec.function!r})\n"
            f"    return _fn({kwargs})"
        )
    return f"def {spec.name}({params}):\n{body}\n"
