"""Generate Hamilton-compatible node modules from config specs."""

import sys
import types
import uuid
from importlib import import_module
from typing import TYPE_CHECKING, Annotated, Any

import xarray as xr
from hamilton.function_modifiers import tag
from xarray_annotated.schema import Coords, Dims, Dtype, declare_schema
from xarray_annotated.units import declare_units

if TYPE_CHECKING:
    from conduit.config import NodeSpec

#: Hamilton tag marking a node whose output preserves its input's declared
#: contract (units/dims/dtype). The contract check reads this to propagate a
#: declaration across the node instead of requiring a fixed one. See
#: `conduit.dag.contract_check`.
PASSTHROUGH_TAG = "conduit_passthrough"


def make_node_module(node_specs: list["NodeSpec"]) -> types.ModuleType:
    """Generate a Hamilton-compatible module with one function per node spec."""
    mod = types.ModuleType(f"conduit_node_generated_{uuid.uuid4().hex[:8]}")
    ns: dict = {
        "xr": xr,
        "Any": Any,
        "Annotated": Annotated,
        "declare_units": declare_units,
        "declare_schema": declare_schema,
        "Dims": Dims,
        "Coords": Coords,
        "Dtype": Dtype,
        "tag": tag,
        "import_module": import_module,
        # Available to node expressions (e.g. the [[resample]] preset desugars to
        # ``__transforms.resample(...)``).
        "__transforms": import_module("conduit.transforms"),
    }
    for spec in node_specs:
        exec(_build_fn_code(spec), ns)
        fn = ns[spec.name]
        fn.__module__ = mod.__name__
        setattr(mod, spec.name, fn)
    sys.modules[mod.__name__] = mod
    return mod


def _return_annotation(spec: "NodeSpec") -> str:
    """Return the ``Annotated[...]`` type carrying the node's declared contract."""
    markers: list[str] = []
    if spec.units is not None:
        markers.append(repr(spec.units))
    if spec.dims:
        markers.append(f"Dims({', '.join(map(repr, spec.dims))})")
    if spec.dtype is not None:
        markers.append(f"Dtype({spec.dtype!r})")
    if spec.coords:
        markers.append(f"Coords({', '.join(map(repr, spec.coords))})")
    if not markers:
        return "xr.DataArray"
    return f"Annotated[xr.DataArray, {', '.join(markers)}]"


def _build_fn_code(spec: "NodeSpec") -> str:
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

    # A passthrough node preserves its input's contract, so it declares none of
    # its own; it is tagged so the contract check propagates the declaration
    # across it (the shape the [[resample]] preset generates).
    if spec.passthrough:
        decorator = f"@tag({PASSTHROUGH_TAG}='true')\n"
        ret_ann = "xr.DataArray"
        return f"{decorator}def {spec.name}({params}) -> {ret_ann}:\n{body}\n"

    # Otherwise a declared unit/dims/dtype/coords makes the node a typed producer:
    # validated/stamped at runtime (@declare_units / @declare_schema) and read by
    # the build-time contract check. Without any, it is an unchecked pass-through.
    ret_ann = _return_annotation(spec)
    decorators = ""
    if spec.units is not None:
        decorators += "@declare_units\n"
    if spec.dims or spec.dtype or spec.coords:
        decorators += "@declare_schema\n"
    return f"{decorators}def {spec.name}({params}) -> {ret_ann}:\n{body}\n"
