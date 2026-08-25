"""Hamilton nodes for the Pipeline 101 recipe.

An ordinary xarray function is an ordinary DAG node: the function name is the
node name, and each parameter name is the node it consumes. The annotations
declare the units conduit checks across the whole DAG before anything runs.
"""

from typing import Annotated

import xarray as xr
from xarray_annotated.units import Unit, declare_units, use_cf_units

use_cf_units()
xr.set_options(keep_attrs=True)

Temperature = Annotated[xr.DataArray, Unit("degC")]


@declare_units
def temperature_anomaly_climate(temperature_climate: Temperature) -> Temperature:
    """Departure of each day's temperature from the record mean."""
    return temperature_climate - temperature_climate.mean("time")
