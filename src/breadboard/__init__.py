"""breadboard: an opinionated Hamilton + xarray + pint foundation for data pipelines."""

from ._version import __version__
from .config import (
    BlockingSpec,
    CacheSpec,
    IOSpec,
    ParsedConfig,
    ResampleSpec,
    SubsetSpec,
    load_config,
)
from .dag._utils import declare_units
from .dag.driver import build_driver
from .io import (
    create_output_store,
    get_final_vars,
    get_outputs,
    load_inputs,
    merge_subset_outputs,
    save_outputs,
)
from .units import UnitsWarning

__all__ = [
    "BlockingSpec",
    "CacheSpec",
    "IOSpec",
    "ParsedConfig",
    "ResampleSpec",
    "SubsetSpec",
    "UnitsWarning",
    "__version__",
    "build_driver",
    "create_output_store",
    "declare_units",
    "get_final_vars",
    "get_outputs",
    "load_config",
    "load_inputs",
    "merge_subset_outputs",
    "save_outputs",
]
