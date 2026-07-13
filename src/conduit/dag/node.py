"""Generate Hamilton-compatible node modules from config specs."""

import hashlib
import sys
import types
from dataclasses import astuple
from importlib import import_module
from typing import TYPE_CHECKING, Any

import xarray as xr
from hamilton.function_modifiers import tag
from xarray_annotated import annotate
from xarray_annotated.schema import declare_schema
from xarray_annotated.temporal import declare_freq
from xarray_annotated.units import declare_units

if TYPE_CHECKING:
    from conduit.specs import NodeSpec

#: Hamilton tag marking a node whose output preserves its input's declared contract.
#: The contract check reads it to propagate that declaration across the node — see
#: `conduit.dag.contract_check` for the semantics (notably that it is per facet).
PASSTHROUGH_TAG = "conduit_passthrough"

#: Names bound in every generated module's namespace, and therefore unusable as a
#: node name or node input: a node called ``xr`` would shadow the helper for every
#: later node's expression. `conduit.specs.NodeSpec.from_config` rejects them at
#: parse time. Kept in step with `_node_namespace` by
#: ``test_dag_node.py::test_reserved_names_match_generated_namespace``.
RESERVED_NODE_NAMES: frozenset[str] = frozenset(
    {"xr", "Any", "import_module", "__transforms"}
)


def _node_namespace() -> dict[str, Any]:
    """Build the namespace every generated node's body is ``exec``'d in."""
    return {
        "xr": xr,
        "Any": Any,
        "import_module": import_module,
        # Available to node expressions (e.g. the [[resample]] preset desugars to
        # ``__transforms.resample(...)``).
        "__transforms": import_module("conduit.transforms"),
    }


def _module_name(node_specs: list["NodeSpec"]) -> str:
    """Return a stable module name, keyed on the specs it is generated from.

    Hamilton requires the generated module to live in ``sys.modules`` (it resolves a
    node's originating function through it), so the registration cannot simply be
    dropped. A random per-build name would therefore leak one entry *per build* —
    unbounded in a long-lived process such as a calibration loop or a test session.

    Keying the name on the specs' content means rebuilding the same config reuses one
    entry, while two different configs still get distinct modules.
    """
    payload = repr([astuple(spec) for spec in node_specs]).encode()
    return f"conduit_node_generated_{hashlib.sha256(payload).hexdigest()[:12]}"


def make_node_module(node_specs: list["NodeSpec"]) -> types.ModuleType:
    """Generate a Hamilton-compatible module with one function per node spec.

    The node's *body* is built by ``exec`` (a ``[[node]]`` expression is arbitrary
    user code), but its declared output contract is attached programmatically:
    ``xarray_annotated.annotate`` builds the ``Annotated`` return hint from the raw
    spec values, then ``declare_units`` / ``declare_schema`` are applied as ordinary
    decorators — no annotation/decorator source is generated.

    The module is registered in ``sys.modules`` under a content-derived name (see
    `_module_name`), which Hamilton requires and which keeps repeated builds of the
    same config from accumulating entries.
    """
    mod = types.ModuleType(_module_name(node_specs))
    ns: dict = _node_namespace()
    for spec in node_specs:
        exec(_build_fn_code(spec), ns)
        fn = _decorate(ns[spec.name], spec)
        fn.__module__ = mod.__name__
        setattr(mod, spec.name, fn)
    sys.modules[mod.__name__] = mod
    return mod


def _decorate(fn: Any, spec: "NodeSpec") -> Any:
    """Attach the node's declared output contract to the bare ``exec``'d function."""
    # A passthrough declares no contract of its own except its frequency (the one
    # facet it does not preserve), and is tagged for the check to propagate the rest.
    if spec.passthrough:
        fn.__annotations__["return"] = annotate(freq=spec.freq)
        if spec.freq is not None:
            fn = declare_freq(fn)
        return tag(**{PASSTHROUGH_TAG: "true"})(fn)  # type: ignore[reportArgumentType]

    # Otherwise a declared unit/dims/dtype/coords/freq makes the node a typed producer:
    # stamped/validated at runtime and read by the build-time check. Without any, the
    # node is simply unchecked.
    fn.__annotations__["return"] = annotate(
        unit=spec.units,
        dims=spec.dims or None,
        dtype=spec.dtype,
        coords=spec.coords or None,
        freq=spec.freq,
    )
    # Apply the validate-only decorators first, then units, so the composition is
    # ``declare_units(declare_freq(declare_schema(fn)))`` (declare_units outermost,
    # as it is the only one that may convert).
    if spec.dims or spec.dtype or spec.coords:
        fn = declare_schema(fn)
    if spec.freq is not None:
        fn = declare_freq(fn)
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
