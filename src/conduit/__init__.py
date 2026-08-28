"""conduit: an opinionated foundation for configurable data pipelines.

Integrates Apache Hamilton (DAG execution), xarray (+ dask) and xarray-annotated
(units / dims / coords / dtype / frequency contracts), driven by a TOML spec.
"""

from xarray_annotated.units import use_cf_units

from ._version import __version__
from .build import build_driver
from .config import load_config
from .graph import build_graph
from .io import (
    get_final_vars,
    get_outputs,
    load_inputs,
    save_outputs,
)
from .pipeline import DryRunReport, RunReport, Stage, WrittenOutput, dry_run, run
from .specs import (
    AnnotationPolicySpec,
    BlockingSpec,
    CacheSpec,
    CheckSpec,
    IOSpec,
    NodeSpec,
    ParsedConfig,
    ResampleSpec,
    SubsetSpec,
)

use_cf_units()

__all__ = [
    "AnnotationPolicySpec",
    "BlockingSpec",
    "CacheSpec",
    "CheckSpec",
    "DryRunReport",
    "IOSpec",
    "NodeSpec",
    "ParsedConfig",
    "ResampleSpec",
    "RunReport",
    "Stage",
    "SubsetSpec",
    "WrittenOutput",
    "__version__",
    "build_driver",
    "build_graph",
    "dry_run",
    "get_final_vars",
    "get_outputs",
    "load_config",
    "load_inputs",
    "run",
    "save_outputs",
]
