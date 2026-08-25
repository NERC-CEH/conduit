---
title: Flux processing with conduit
icon: lucide/workflow
---

# Flux processing with conduit

This recipe turns the eddy-covariance flux workflow from the
[xarray-annotated worked example](https://github.com/jmarshrossney/xarray-annotated/blob/main/examples/notebook.py)
into a conduit pipeline. It is split across four files:

- `nodes.py`: ordinary, annotated Hamilton node functions;
- `config.toml`: the pipeline wiring, inputs, and outputs;
- `make_data.py`: a generator for the synthetic inputs;
- `demo.py`: a marimo walkthrough of the same pipeline through the Python API.

The example files live in
[`recipes/flux_pipeline`](https://github.com/NERC-CEH/conduit/tree/main/recipes/flux_pipeline).
Everything below runs from the command line; the notebook is another view of the same
pipeline, not a prerequisite. To open it, run this from the repository root:

```sh
uv run marimo run recipes/flux_pipeline/demo.py
```

!!! note "Requirements"

    Install the documentation dependencies with `uv sync --group docs`. Graph generation
    also requires the Graphviz system executable; see the
    [installation guide](../guides/install.md).

## Pipeline configuration

The TOML imports the Python module as a user module. Input and output paths resolve
relative to this file, as in every conduit configuration.

```toml
--8<-- "recipes/flux_pipeline/config.toml"
```

The complete file is available at
[`config.toml`](https://github.com/NERC-CEH/conduit/blob/main/recipes/flux_pipeline/config.toml).

## Python module

`recipes.flux_pipeline.nodes` is an ordinary importable Python module. The
`[flux_nodes]` section in the TOML imports it with `_import_path`, and Hamilton picks up
the public functions below as pipeline nodes. Their annotations are the contracts the
whole-DAG check uses.

Here is the whole module, so the implementation and its annotations can be read
together:

```python
--8<-- "recipes/flux_pipeline/nodes.py"
```

## Running the pipeline

Every command below runs when the documentation is built, from the repository root.
The output on this page is what conduit printed.

`config.toml` names its node module as `_import_path = "recipes.flux_pipeline.nodes"`,
which conduit resolves as an ordinary Python import. That module is not installed, so it
resolves against the working directory, which conduit appends to `sys.path`. An
installed package of the same name would win, and `PYTHONSAFEPATH=1` turns the working
directory off entirely.

First generate the synthetic inputs. `make_data.py` writes a year of half-hourly
eddy-covariance data and weekly satellite GPP, from a fixed seed, so the products
further down are reproducible.

```bash exec="true" source="material-block"
python recipes/flux_pipeline/make_data.py
```

`conduit graph` renders the DAG. Each node carries its declared unit, and edges are
coloured by temporal frequency, both taken from the annotations in `nodes.py`.

```bash exec="true" source="material-block"
conduit graph recipes/flux_pipeline/config.toml --png \
  --output recipes/flux_pipeline/pipeline
```

`conduit run --dry-run` parses the config, opens the inputs, builds the DAG, and runs the
whole-DAG contract check, all before any array is computed. A unit or frequency mismatch
anywhere in the graph fails here rather than after several minutes of work.

```bash exec="true" source="material-block"
conduit run --dry-run recipes/flux_pipeline/config.toml
```

### The conversion the dry run reported

That `!` line under the contract check is worth reading.
`data/flux.nc` stores air temperature in kelvin:

```bash exec="true" source="material-block"
python -c "
import xarray as xr
with xr.open_dataset('recipes/flux_pipeline/data/flux.nc') as ds:
    print(ds.tair.attrs['units'], float(ds.tair.min()).__round__(1), 'to', float(ds.tair.max()).__round__(1))
"
```

but `partition_fluxes` declares `tair: Annotated[xr.DataArray, Unit("degC")]`, and its
respiration term is `2.60 * 2.0 ** ((tair - 10.0) / 10.0)`, a $Q_{10}$ relation written
for degrees Celsius. Handed kelvin it would return respiration around $10^8$ rather than
$4$, and nothing downstream would look obviously wrong.

`declare_units` is the outermost decorator on the node so that it can convert rather than
only validate. The units are compatible but not equal, so the offset is applied and the
node receives Celsius. The declaration is what makes the conversion happen; a bare `tair`
parameter would have quietly used kelvin.

`config.toml` sets `on_inexact = "warn"`, which is why the conversion is named in the
output above rather than done in silence. The `units` row of the policy block reports the
setting in force, so the report says which rules it applied instead of leaving you to
work them out from the config. The default, `"convert"`, would have done the same
arithmetic without saying so.

That matters because pint's notion of compatibility is dimensional. `g m-2 d-1` and
`g m-2 yr-1` are both mass per area per time, so a daily rate declared as an annual one
converts happily, off by a factor of 365.25. `"warn"` makes every value-changing
conversion visible so the ones you did not intend stand out; `"error"` refuses them
outright.

Then execute it for real.

```bash exec="true" source="material-block"
conduit run recipes/flux_pipeline/config.toml
ls -1 recipes/flux_pipeline/results/
```

The products land in a single NetCDF file, one variable per requested output.

```bash exec="true" source="material-block"
python - <<'EOF'
import xarray as xr

with xr.open_dataset("recipes/flux_pipeline/results/flux_products.nc") as ds:
    for name, da in ds.items():
        print(f"{name:12s} {str(da.dims):16s} {da.attrs.get('units', '-')}")
EOF
```

## Watching the contract check fail

The check above passed, which tells you little. `broken.toml` is the same pipeline with
one mistake in it:

```toml
--8<-- "recipes/flux_pipeline/broken.toml"
```

A stand-in for the satellite retrieval is built from the modelled weekly GPP, but
declared in `umol m-2 s-1`, the units of the molar flux several nodes upstream, rather
than the `g m-2 d-1` that `compare_with_satellite` consumes. Read either declaration on
its own and nothing looks wrong. They are only inconsistent with each other.

```bash exec="true" source="material-block" returncode="1"
conduit run --dry-run recipes/flux_pipeline/broken.toml
```

The message names both ends of the edge and why they cannot be reconciled: knowing that
`sat_gpp` is wrong is not much use without knowing what disagreed with it. And it fails
during DAG construction, before the inputs are read and long before an array is computed,
so the mistake costs a second rather than however long the pipeline takes.

Had the units been *inexact* rather than incompatible, `umol m-2 s-1` against
`nmol m-2 s-1` say, this would have converted silently, as `tair` does above. The check
flags an edge only when the two declarations are provably irreconcilable, which is what
lets a partly-annotated pipeline adopt it without a wave of false positives.

## What the notebook adds

The [exported notebook](flux-pipeline-demo.md) covers the same ground through conduit's
Python API rather than the CLI, and renders the DAG image and the product time series
inline. Read it to see how the same nodes are driven from a Python session; use the
commands above for the config-driven path.

The node functions do not care either way. They are ordinary annotated xarray functions,
reusable from another config or imported directly.
