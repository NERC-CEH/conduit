"""Generate Hamilton-compatible node modules from config specs."""

import sys
import types
import uuid
from importlib import import_module
from typing import TYPE_CHECKING, Annotated, Any

import xarray as xr

from ._utils import declare_units

if TYPE_CHECKING:
    from satterc.config import NodeSpec


def make_node_module(node_specs: list["NodeSpec"]) -> types.ModuleType:
    """Generate a Hamilton-compatible module with one function per node spec."""
    mod = types.ModuleType(f"satterc_node_generated_{uuid.uuid4().hex[:8]}")
    ns: dict = {
        "xr": xr,
        "Any": Any,
        "Annotated": Annotated,
        "declare_units": declare_units,
        "import_module": import_module,
    }
    for spec in node_specs:
        exec(_build_fn_code(spec), ns)
        fn = ns[spec.name]
        fn.__module__ = mod.__name__
        setattr(mod, spec.name, fn)
    sys.modules[mod.__name__] = mod
    return mod


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
    # A declared unit makes the node a typed producer: it is stamped onto the
    # output at runtime (@declare_units) and read by the build-time DAG check.
    # Without it the node is a unit-unknown pass-through (no static coverage).
    if spec.units is not None:
        ret_ann = f"Annotated[xr.DataArray, {spec.units!r}]"
        decorator = "@declare_units\n"
    else:
        ret_ann = "xr.DataArray"
        decorator = ""
    return f"{decorator}def {spec.name}({params}) -> {ret_ann}:\n{body}\n"
