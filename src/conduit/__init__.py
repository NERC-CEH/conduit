"""conduit: an opinionated Hamilton + xarray + pint foundation for data pipelines."""

from xarray_annotated.schema import (
    Coords,
    Dims,
    Dtype,
    SchemaWarning,
    declare_schema,
)
from xarray_annotated.units import UnitsWarning, declare_units, use_cf_units

from ._version import __version__
from .config import load_config
from .dag.driver import build_driver
from .io import (
    get_final_vars,
    get_outputs,
    load_inputs,
    save_outputs,
)
from .specs import (
    AnnotationPolicySpec,
    BlockingSpec,
    CacheSpec,
    IOSpec,
    ParsedConfig,
    ResampleSpec,
    SubsetSpec,
)

use_cf_units()

__all__ = [
    "AnnotationPolicySpec",
    "BlockingSpec",
    "CacheSpec",
    "Coords",
    "Dims",
    "Dtype",
    "IOSpec",
    "ParsedConfig",
    "ResampleSpec",
    "SchemaWarning",
    "SubsetSpec",
    "UnitsWarning",
    "__version__",
    "build_driver",
    "declare_schema",
    "declare_units",
    "get_final_vars",
    "get_outputs",
    "load_config",
    "load_inputs",
    "save_outputs",
]
