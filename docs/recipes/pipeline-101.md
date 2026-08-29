---
title: Pipeline 101
marimo-version: 0.23.14

  """Executable walkthrough of the smallest complete conduit pipeline."""
---

```python {.marimo}
from pathlib import Path

import marimo as mo

recipe_dir = Path(__file__).parent
project_dir = recipe_dir.parents[1]
config_path = recipe_dir / "config.toml"
nodes_path = recipe_dir / "nodes.py"
data_dir = recipe_dir / "data"
results_dir = recipe_dir / "results"
data_dir.mkdir(exist_ok=True)
results_dir.mkdir(exist_ok=True)

def rel(path):
    """Path relative to the repository root, so output is machine-independent."""
    return Path(path).relative_to(project_dir)
```

# Pipeline 101

The smallest pipeline that still has every moving part: an input file, a
node function imported from a Python module, a node defined inline in the
config, and an output file.

It derives a temperature anomaly from 90 days of daily temperature at three
sites, then reduces the anomaly to a per-site range.

Everything below drives the library directly, so nothing here needs the
`conduit` command installed.
<!---->
## The input

`make_data.py` writes a deterministic NetCDF file next to this notebook. The
`units` attribute on the variable is what lets conduit check the pipeline's
unit contracts against the file before running anything.

```python {.marimo}
from conduit.importing import import_user_module

# make_data.py sits next to this notebook. This is the same loader conduit uses
# for an `_import_path` naming a .py file, so nothing goes on sys.path.
make_data = import_user_module(str(recipe_dir / "make_data.py"))

rel(make_data.write_inputs(data_dir))
```

<!-- @output:bkHC -->

<pre style="white-space: pre-wrap; overflow-wrap: break-word;">PosixPath(&#x27;recipes/pipeline_101/data/climate.nc&#x27;)</pre>

<!-- @output:lEQa -->

<span class="markdown prose dark:prose-invert contents"><h2 id="the-node-module">The node module</h2>
<span class="paragraph">An ordinary xarray function is an ordinary DAG node. The function name is
the node name, each parameter name is the node it consumes, and the
annotations declare the units.</span>
<div class="language-python codehilite"><pre><span></span><code><span class="sd">"""Hamilton nodes for the Pipeline 101 recipe.</span>

<span class="sd">An ordinary xarray function is an ordinary DAG node: the function name is the</span>
<span class="sd">node name, and each parameter name is the node it consumes. The annotations</span>
<span class="sd">declare the units conduit checks across the whole DAG before anything runs.</span>
<span class="sd">"""</span>

<span class="kn">from</span><span class="w"> </span><span class="nn">typing</span><span class="w"> </span><span class="kn">import</span> <span class="n">Annotated</span>

<span class="kn">import</span><span class="w"> </span><span class="nn">xarray</span><span class="w"> </span><span class="k">as</span><span class="w"> </span><span class="nn">xr</span>
<span class="kn">from</span><span class="w"> </span><span class="nn">xarray_annotated.units</span><span class="w"> </span><span class="kn">import</span> <span class="n">Unit</span><span class="p">,</span> <span class="n">declare_units</span><span class="p">,</span> <span class="n">use_cf_units</span>

<span class="n">use_cf_units</span><span class="p">()</span>
<span class="n">xr</span><span class="o">.</span><span class="n">set_options</span><span class="p">(</span><span class="n">keep_attrs</span><span class="o">=</span><span class="kc">True</span><span class="p">)</span>

<span class="n">Temperature</span> <span class="o">=</span> <span class="n">Annotated</span><span class="p">&#91;</span><span class="n">xr</span><span class="o">.</span><span class="n">DataArray</span><span class="p">,</span> <span class="n">Unit</span><span class="p">(</span><span class="s2">"degC"</span><span class="p">)&#93;</span>

<span class="nd">@declare_units</span>
<span class="k">def</span><span class="w"> </span><span class="nf">temperature_anomaly_climate</span><span class="p">(</span><span class="n">temperature_climate</span><span class="p">:</span> <span class="n">Temperature</span><span class="p">)</span> <span class="o">-></span> <span class="n">Temperature</span><span class="p">:</span>
<span class="w">    </span><span class="sd">"""Departure of each day's temperature from the record mean."""</span>
    <span class="k">return</span> <span class="n">temperature_climate</span> <span class="o">-</span> <span class="n">temperature_climate</span><span class="o">.</span><span class="n">mean</span><span class="p">(</span><span class="s2">"time"</span><span class="p">)</span>
</code></pre></div></span>

<!-- @output:PKri -->

<span class="markdown prose dark:prose-invert contents"><h2 id="the-config">The config</h2>
<span class="paragraph">Three kinds of section, and between them they describe the whole graph.</span>
<div class="language-toml codehilite"><pre><span></span><code><span class="c1"># The smallest pipeline that still has every moving part: an input file, an</span>
<span class="c1"># imported node function, an inline node, and an output file.</span>

<span class="k">&#91;inputs.climate&#93;</span>
<span class="n">path</span><span class="w"> </span><span class="o">=</span><span class="w"> </span><span class="s2">"data/climate.nc"</span>
<span class="n">vars</span><span class="w"> </span><span class="o">=</span><span class="w"> </span><span class="p">&#91;</span><span class="s2">"temperature"</span><span class="p">&#93;</span>

<span class="c1"># Any section conduit does not recognise is one of your own modules, and must</span>
<span class="c1"># say where to import it from. A path ending in .py is relative to this file.</span>
<span class="k">&#91;climate_nodes&#93;</span>
<span class="n">_import_path</span><span class="w"> </span><span class="o">=</span><span class="w"> </span><span class="s2">"nodes.py"</span>

<span class="c1"># Glue that does not deserve a Python module can be declared inline.</span>
<span class="k">&#91;&#91;node&#93;&#93;</span>
<span class="n">name</span><span class="w"> </span><span class="o">=</span><span class="w"> </span><span class="s2">"anomaly_range_climate"</span>
<span class="n">inputs</span><span class="w"> </span><span class="o">=</span><span class="w"> </span><span class="p">&#91;</span><span class="s2">"temperature_anomaly_climate"</span><span class="p">&#93;</span>
<span class="n">expression</span><span class="w"> </span><span class="o">=</span><span class="w"> </span><span class="s2">"temperature_anomaly_climate.max('time') - temperature_anomaly_climate.min('time')"</span>
<span class="n">units</span><span class="w"> </span><span class="o">=</span><span class="w"> </span><span class="s2">"degC"</span>

<span class="k">&#91;outputs.climate&#93;</span>
<span class="n">path</span><span class="w"> </span><span class="o">=</span><span class="w"> </span><span class="s2">"results/anomaly.nc"</span>
<span class="n">vars</span><span class="w"> </span><span class="o">=</span><span class="w"> </span><span class="p">{</span><span class="w"> </span><span class="n">temperature_anomaly_climate</span><span class="w"> </span><span class="p">=</span><span class="w"> </span><span class="s2">"temperature_anomaly"</span><span class="p">,</span><span class="w"> </span><span class="n">anomaly_range_climate</span><span class="w"> </span><span class="p">=</span><span class="w"> </span><span class="s2">"anomaly_range"</span><span class="w"> </span><span class="p">}</span>
</code></pre></div></span>

## The graph conduit builds

`conduit.build_graph` returns a `graphviz.Digraph` without running anything, so
it renders inline. Node labels carry the declared units, so a wiring mistake is
often visible before a dry run reports it.

```python {.marimo}
import conduit

graph = conduit.build_graph(config_path)
graph
```

<!-- @output:SFPL -->

<img src="data:image/svg+xml,%3C%3Fxml%20version%3D%221.0%22%20encoding%3D%22UTF-8%22%20standalone%3D%22no%22%3F%3E%0A%3C%21DOCTYPE%20svg%20PUBLIC%20%22-%2F%2FW3C%2F%2FDTD%20SVG%201.1%2F%2FEN%22%0A%20%22http%3A%2F%2Fwww.w3.org%2FGraphics%2FSVG%2F1.1%2FDTD%2Fsvg11.dtd%22%3E%0A%3C%21--%20Generated%20by%20graphviz%20version%202.43.0%20%280%29%0A%20--%3E%0A%3C%21--%20Title%3A%20%253%20Pages%3A%201%20--%3E%0A%3Csvg%20width%3D%22823pt%22%20height%3D%22271pt%22%0A%20viewBox%3D%220.00%200.00%20823.00%20271.00%22%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20xmlns%3Axlink%3D%22http%3A%2F%2Fwww.w3.org%2F1999%2Fxlink%22%3E%0A%3Cg%20id%3D%22graph0%22%20class%3D%22graph%22%20transform%3D%22scale%281%201%29%20rotate%280%29%20translate%284%20267%29%22%3E%0A%3Ctitle%3E%253%3C%2Ftitle%3E%0A%3Cpolygon%20fill%3D%22white%22%20stroke%3D%22transparent%22%20points%3D%22-4%2C4%20-4%2C-267%20819%2C-267%20819%2C4%20-4%2C4%22%2F%3E%0A%3Cg%20id%3D%22clust1%22%20class%3D%22cluster%22%3E%0A%3Ctitle%3Ecluster__legend%3C%2Ftitle%3E%0A%3Cpolygon%20fill%3D%22%23ffffff%22%20stroke%3D%22black%22%20points%3D%22103.5%2C-123%20103.5%2C-255%20187.5%2C-255%20187.5%2C-123%20103.5%2C-123%22%2F%3E%0A%3Ctext%20text-anchor%3D%22middle%22%20x%3D%22145.5%22%20y%3D%22-239.8%22%20font-family%3D%22Helvetica%2Csans-Serif%22%20font-size%3D%2214.00%22%3ELegend%3C%2Ftext%3E%0A%3C%2Fg%3E%0A%3C%21--%20hamilton.enable_power_user_mode%20--%3E%0A%3Cg%20id%3D%22node1%22%20class%3D%22node%22%3E%0A%3Ctitle%3Ehamilton.enable_power_user_mode%3C%2Ftitle%3E%0A%3Cpolygon%20fill%3D%22%23ffffff%22%20stroke%3D%22black%22%20points%3D%22285%2C-50%200%2C-50%200%2C0%20291%2C0%20291%2C-44%20285%2C-50%22%2F%3E%0A%3Cpolyline%20fill%3D%22none%22%20stroke%3D%22black%22%20points%3D%22285%2C-50%20285%2C-44%20%22%2F%3E%0A%3Cpolyline%20fill%3D%22none%22%20stroke%3D%22black%22%20points%3D%22291%2C-44%20285%2C-44%20%22%2F%3E%0A%3Ctext%20text-anchor%3D%22start%22%20x%3D%228%22%20y%3D%22-35.8%22%20font-family%3D%22Helvetica%2Csans-Serif%22%20font-weight%3D%22bold%22%20font-size%3D%2214.00%22%3Ehamilton.enable_power_user_mode%3C%2Ftext%3E%0A%3Ctext%20text-anchor%3D%22start%22%20x%3D%22130%22%20y%3D%22-7.8%22%20font-family%3D%22Helvetica%2Csans-Serif%22%20font-style%3D%22italic%22%20font-size%3D%2214.00%22%3ETrue%3C%2Ftext%3E%0A%3C%2Fg%3E%0A%3C%21--%20temperature_anomaly_climate%20--%3E%0A%3Cg%20id%3D%22node2%22%20class%3D%22node%22%3E%0A%3Ctitle%3Etemperature_anomaly_climate%3C%2Ftitle%3E%0A%3Cpath%20fill%3D%22%23b4d8e4%22%20stroke%3D%22%23e7298a%22%20stroke-width%3D%222.5%22%20d%3D%22M568%2C-123C568%2C-123%20332%2C-123%20332%2C-123%20326%2C-123%20320%2C-117%20320%2C-111%20320%2C-111%20320%2C-71%20320%2C-71%20320%2C-65%20326%2C-59%20332%2C-59%20332%2C-59%20568%2C-59%20568%2C-59%20574%2C-59%20580%2C-65%20580%2C-71%20580%2C-71%20580%2C-111%20580%2C-111%20580%2C-117%20574%2C-123%20568%2C-123%22%2F%3E%0A%3Ctext%20text-anchor%3D%22start%22%20x%3D%22331%22%20y%3D%22-101.8%22%20font-family%3D%22Helvetica%2Csans-Serif%22%20font-weight%3D%22bold%22%20font-size%3D%2214.00%22%3Etemperature_anomaly_climate%3C%2Ftext%3E%0A%3Ctext%20text-anchor%3D%22start%22%20x%3D%22431.5%22%20y%3D%22-73.8%22%20font-family%3D%22Helvetica%2Csans-Serif%22%20font-style%3D%22italic%22%20font-size%3D%2214.00%22%3EdegC%3C%2Ftext%3E%0A%3C%2Fg%3E%0A%3C%21--%20anomaly_range_climate%20--%3E%0A%3Cg%20id%3D%22node3%22%20class%3D%22node%22%3E%0A%3Ctitle%3Eanomaly_range_climate%3C%2Ftitle%3E%0A%3Cpath%20fill%3D%22%23b4d8e4%22%20stroke%3D%22%23e7298a%22%20stroke-width%3D%222.5%22%20d%3D%22M803%2C-123C803%2C-123%20621%2C-123%20621%2C-123%20615%2C-123%20609%2C-117%20609%2C-111%20609%2C-111%20609%2C-71%20609%2C-71%20609%2C-65%20615%2C-59%20621%2C-59%20621%2C-59%20803%2C-59%20803%2C-59%20809%2C-59%20815%2C-65%20815%2C-71%20815%2C-71%20815%2C-111%20815%2C-111%20815%2C-117%20809%2C-123%20803%2C-123%22%2F%3E%0A%3Ctext%20text-anchor%3D%22start%22%20x%3D%22620%22%20y%3D%22-101.8%22%20font-family%3D%22Helvetica%2Csans-Serif%22%20font-weight%3D%22bold%22%20font-size%3D%2214.00%22%3Eanomaly_range_climate%3C%2Ftext%3E%0A%3Ctext%20text-anchor%3D%22start%22%20x%3D%22693.5%22%20y%3D%22-73.8%22%20font-family%3D%22Helvetica%2Csans-Serif%22%20font-style%3D%22italic%22%20font-size%3D%2214.00%22%3EdegC%3C%2Ftext%3E%0A%3C%2Fg%3E%0A%3C%21--%20temperature_anomaly_climate%26%2345%3B%26gt%3Banomaly_range_climate%20--%3E%0A%3Cg%20id%3D%22edge2%22%20class%3D%22edge%22%3E%0A%3Ctitle%3Etemperature_anomaly_climate%26%2345%3B%26gt%3Banomaly_range_climate%3C%2Ftitle%3E%0A%3Cpath%20fill%3D%22none%22%20stroke%3D%22black%22%20d%3D%22M580.24%2C-91C586.36%2C-91%20592.49%2C-91%20598.56%2C-91%22%2F%3E%0A%3Cpolygon%20fill%3D%22black%22%20stroke%3D%22black%22%20points%3D%22598.72%2C-94.5%20608.72%2C-91%20598.72%2C-87.5%20598.72%2C-94.5%22%2F%3E%0A%3C%2Fg%3E%0A%3C%21--%20_temperature_anomaly_climate_inputs%20--%3E%0A%3Cg%20id%3D%22node4%22%20class%3D%22node%22%3E%0A%3Ctitle%3E_temperature_anomaly_climate_inputs%3C%2Ftitle%3E%0A%3Cpolygon%20fill%3D%22%23ffffff%22%20stroke%3D%22black%22%20stroke-dasharray%3D%225%2C2%22%20points%3D%22254%2C-113.5%2037%2C-113.5%2037%2C-68.5%20254%2C-68.5%20254%2C-113.5%22%2F%3E%0A%3Ctext%20text-anchor%3D%22start%22%20x%3D%2252.5%22%20y%3D%22-86.8%22%20font-family%3D%22Helvetica%2Csans-Serif%22%20font-size%3D%2214.00%22%3Etemperature_climate%3C%2Ftext%3E%0A%3Ctext%20text-anchor%3D%22start%22%20x%3D%22202.5%22%20y%3D%22-86.8%22%20font-family%3D%22Helvetica%2Csans-Serif%22%20font-size%3D%2214.00%22%3EdegC%3C%2Ftext%3E%0A%3C%2Fg%3E%0A%3C%21--%20_temperature_anomaly_climate_inputs%26%2345%3B%26gt%3Btemperature_anomaly_climate%20--%3E%0A%3Cg%20id%3D%22edge1%22%20class%3D%22edge%22%3E%0A%3Ctitle%3E_temperature_anomaly_climate_inputs%26%2345%3B%26gt%3Btemperature_anomaly_climate%3C%2Ftitle%3E%0A%3Cpath%20fill%3D%22none%22%20stroke%3D%22black%22%20d%3D%22M254%2C-91C272.07%2C-91%20291.04%2C-91%20309.77%2C-91%22%2F%3E%0A%3Cpolygon%20fill%3D%22black%22%20stroke%3D%22black%22%20points%3D%22309.84%2C-94.5%20319.84%2C-91%20309.84%2C-87.5%20309.84%2C-94.5%22%2F%3E%0A%3C%2Fg%3E%0A%3C%21--%20input%20--%3E%0A%3Cg%20id%3D%22node5%22%20class%3D%22node%22%3E%0A%3Ctitle%3Einput%3C%2Ftitle%3E%0A%3Cpolygon%20fill%3D%22%23ffffff%22%20stroke%3D%22black%22%20stroke-dasharray%3D%225%2C2%22%20points%3D%22175%2C-223.5%20116%2C-223.5%20116%2C-186.5%20175%2C-186.5%20175%2C-223.5%22%2F%3E%0A%3Ctext%20text-anchor%3D%22middle%22%20x%3D%22145.5%22%20y%3D%22-201.3%22%20font-family%3D%22Helvetica%2Csans-Serif%22%20font-size%3D%2214.00%22%3Einput%3C%2Ftext%3E%0A%3C%2Fg%3E%0A%3C%21--%20output%20--%3E%0A%3Cg%20id%3D%22node6%22%20class%3D%22node%22%3E%0A%3Ctitle%3Eoutput%3C%2Ftitle%3E%0A%3Cpath%20fill%3D%22%23b4d8e4%22%20stroke%3D%22%23e7298a%22%20stroke-width%3D%222.5%22%20d%3D%22M167.5%2C-168.5C167.5%2C-168.5%20123.5%2C-168.5%20123.5%2C-168.5%20117.5%2C-168.5%20111.5%2C-162.5%20111.5%2C-156.5%20111.5%2C-156.5%20111.5%2C-143.5%20111.5%2C-143.5%20111.5%2C-137.5%20117.5%2C-131.5%20123.5%2C-131.5%20123.5%2C-131.5%20167.5%2C-131.5%20167.5%2C-131.5%20173.5%2C-131.5%20179.5%2C-137.5%20179.5%2C-143.5%20179.5%2C-143.5%20179.5%2C-156.5%20179.5%2C-156.5%20179.5%2C-162.5%20173.5%2C-168.5%20167.5%2C-168.5%22%2F%3E%0A%3Ctext%20text-anchor%3D%22middle%22%20x%3D%22145.5%22%20y%3D%22-146.3%22%20font-family%3D%22Helvetica%2Csans-Serif%22%20font-size%3D%2214.00%22%3Eoutput%3C%2Ftext%3E%0A%3C%2Fg%3E%0A%3C%2Fg%3E%0A%3C%2Fsvg%3E%0A" alt="svg+xml">

## Validate, then run

`conduit.dry_run` parses the config, opens the input headers, builds the DAG and
checks every contract, without executing a node. Only then is it worth spending
compute. It returns a `DryRunReport`, one `Stage` per thing it checked.

```python {.marimo}
dry = conduit.dry_run(config_path)

mo.md(
    "| Stage | Status | Detail |\n|---|---|---|\n"
    + "\n".join(
        f"| `{stage.name}` | {stage.status} | {stage.detail} |"
        for stage in dry.stages
    )
)
```

<!-- @output:RGSE -->

<span class="markdown prose dark:prose-invert contents"><table>
<thead>
<tr>
<th>Stage</th>
<th>Status</th>
<th>Detail</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>config</code></td>
<td>ok</td>
<td>config parsed</td>
</tr>
<tr>
<td><code>inputs</code></td>
<td>ok</td>
<td>inputs loaded: 1 variable(s) from 1 source(s)</td>
</tr>
<tr>
<td><code>checks</code></td>
<td>skipped</td>
<td>input checks: none configured</td>
</tr>
<tr>
<td><code>dag</code></td>
<td>ok</td>
<td>DAG built (static contract check passed)</td>
</tr>
<tr>
<td><code>plan</code></td>
<td>ok</td>
<td>execution plan valid: 2 output node(s) reachable</td>
</tr>
<tr>
<td><code>contracts</code></td>
<td>ok</td>
<td>input contracts validated</td>
</tr>
<tr>
<td><code>outputs</code></td>
<td>ok</td>
<td>output paths writable: 1 destination(s)</td>
</tr>
</tbody>
</table></span>

```python {.marimo}
run = conduit.run(config_path)

mo.md(
    f"Completed in {run.elapsed:.2f}s.\n\n"
    "| Written | Variables | Size |\n|---|---|---:|\n"
    + "\n".join(
        f"| `{rel(out.path)}` | {len(out.variables)} | {out.size_bytes / 1000:.1f} kB |"
        for out in run.written
    )
)
```

<!-- @output:Kclp -->

<span class="markdown prose dark:prose-invert contents"><span class="paragraph">Completed in 0.01s.</span>
<table>
<thead>
<tr>
<th>Written</th>
<th>Variables</th>
<th style="text-align: right;">Size</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>recipes/pipeline_101/results/anomaly.nc</code></td>
<td>2</td>
<td style="text-align: right;">13.1 kB</td>
</tr>
</tbody>
</table></span>

```python {.marimo}
result = run.outputs["climate"]
```

<!-- @output:Hstk -->

<span class="markdown prose dark:prose-invert contents"><h2 id="the-output">The output</h2>
<span class="paragraph"><code>run.outputs</code> holds the datasets in memory, carrying the units declared on the
nodes:</span>
<ul>
<li><code>temperature_anomaly</code> — degC</li>
<li><code>anomaly_range</code> — degC</li>
</ul>
<span class="paragraph">Provenance is stamped as the file is written rather than onto the returned
dataset, so it is read back from <code>recipes/pipeline_101/results/anomaly.nc</code>: the config text, and
<code>conduit_config_sha256 = 2f1e7aeb22fc4201…</code></span></span>

```python {.marimo}
result
```

<!-- @output:nWHF -->

<div><svg style="position: absolute; width: 0; height: 0; overflow: hidden">
<defs>
<symbol id="icon-database" viewBox="0 0 32 32">
<path d="M16 0c-8.837 0-16 2.239-16 5v4c0 2.761 7.163 5 16 5s16-2.239 16-5v-4c0-2.761-7.163-5-16-5z"></path>
<path d="M16 17c-8.837 0-16-2.239-16-5v6c0 2.761 7.163 5 16 5s16-2.239 16-5v-6c0 2.761-7.163 5-16 5z"></path>
<path d="M16 26c-8.837 0-16-2.239-16-5v6c0 2.761 7.163 5 16 5s16-2.239 16-5v-6c0 2.761-7.163 5-16 5z"></path>
</symbol>
<symbol id="icon-file-text2" viewBox="0 0 32 32">
<path d="M28.681 7.159c-0.694-0.947-1.662-2.053-2.724-3.116s-2.169-2.030-3.116-2.724c-1.612-1.182-2.393-1.319-2.841-1.319h-15.5c-1.378 0-2.5 1.121-2.5 2.5v27c0 1.378 1.122 2.5 2.5 2.5h23c1.378 0 2.5-1.122 2.5-2.5v-19.5c0-0.448-0.137-1.23-1.319-2.841zM24.543 5.457c0.959 0.959 1.712 1.825 2.268 2.543h-4.811v-4.811c0.718 0.556 1.584 1.309 2.543 2.268zM28 29.5c0 0.271-0.229 0.5-0.5 0.5h-23c-0.271 0-0.5-0.229-0.5-0.5v-27c0-0.271 0.229-0.5 0.5-0.5 0 0 15.499-0 15.5 0v7c0 0.552 0.448 1 1 1h7v19.5z"></path>
<path d="M23 26h-14c-0.552 0-1-0.448-1-1s0.448-1 1-1h14c0.552 0 1 0.448 1 1s-0.448 1-1 1z"></path>
<path d="M23 22h-14c-0.552 0-1-0.448-1-1s0.448-1 1-1h14c0.552 0 1 0.448 1 1s-0.448 1-1 1z"></path>
<path d="M23 18h-14c-0.552 0-1-0.448-1-1s0.448-1 1-1h14c0.552 0 1 0.448 1 1s-0.448 1-1 1z"></path>
</symbol>
</defs>
</svg>
<style>/* CSS stylesheet for displaying xarray objects in notebooks */

:root {
  --xr-font-color0: var(
    --jp-content-font-color0,
    var(--pst-color-text-base rgba(0, 0, 0, 1))
  );
  --xr-font-color2: var(
    --jp-content-font-color2,
    var(--pst-color-text-base, rgba(0, 0, 0, 0.54))
  );
  --xr-font-color3: var(
    --jp-content-font-color3,
    var(--pst-color-text-base, rgba(0, 0, 0, 0.38))
  );
  --xr-border-color: var(
    --jp-border-color2,
    hsl(from var(--pst-color-on-background, white) h s calc(l - 10))
  );
  --xr-disabled-color: var(
    --jp-layout-color3,
    hsl(from var(--pst-color-on-background, white) h s calc(l - 40))
  );
  --xr-background-color: var(
    --jp-layout-color0,
    var(--pst-color-on-background, white)
  );
  --xr-background-color-row-even: var(
    --jp-layout-color1,
    hsl(from var(--pst-color-on-background, white) h s calc(l - 5))
  );
  --xr-background-color-row-odd: var(
    --jp-layout-color2,
    hsl(from var(--pst-color-on-background, white) h s calc(l - 15))
  );
}

html&#91;theme="dark"&#93;,
html&#91;data-theme="dark"&#93;,
body&#91;data-theme="dark"&#93;,
body.vscode-dark {
  --xr-font-color0: var(
    --jp-content-font-color0,
    var(--pst-color-text-base, rgba(255, 255, 255, 1))
  );
  --xr-font-color2: var(
    --jp-content-font-color2,
    var(--pst-color-text-base, rgba(255, 255, 255, 0.54))
  );
  --xr-font-color3: var(
    --jp-content-font-color3,
    var(--pst-color-text-base, rgba(255, 255, 255, 0.38))
  );
  --xr-border-color: var(
    --jp-border-color2,
    hsl(from var(--pst-color-on-background, #111111) h s calc(l + 10))
  );
  --xr-disabled-color: var(
    --jp-layout-color3,
    hsl(from var(--pst-color-on-background, #111111) h s calc(l + 40))
  );
  --xr-background-color: var(
    --jp-layout-color0,
    var(--pst-color-on-background, #111111)
  );
  --xr-background-color-row-even: var(
    --jp-layout-color1,
    hsl(from var(--pst-color-on-background, #111111) h s calc(l + 5))
  );
  --xr-background-color-row-odd: var(
    --jp-layout-color2,
    hsl(from var(--pst-color-on-background, #111111) h s calc(l + 15))
  );
}

.xr-wrap {
  display: block !important;
  min-width: 300px;
  max-width: 700px;
  line-height: 1.6;
  padding-bottom: 4px;
}

.xr-text-repr-fallback {
  /* fallback to plain text repr when CSS is not injected (untrusted notebook) */
  display: none;
}

.xr-header {
  padding-top: 6px;
  padding-bottom: 6px;
}

.xr-header {
  border-bottom: solid 1px var(--xr-border-color);
  margin-bottom: 4px;
}

.xr-header > div,
.xr-header > ul {
  display: inline;
  margin-top: 0;
  margin-bottom: 0;
}

.xr-obj-type,
.xr-obj-name {
  margin-left: 2px;
  margin-right: 10px;
}

.xr-obj-type,
.xr-group-box-contents > label {
  color: var(--xr-font-color2);
  display: block;
}

.xr-sections {
  padding-left: 0 !important;
  display: grid;
  grid-template-columns: 150px auto auto 1fr 0 20px 0 20px;
  margin-block-start: 0;
  margin-block-end: 0;
}

.xr-section-item {
  display: contents;
}

.xr-section-item > input,
.xr-group-box-contents > input,
.xr-array-wrap > input {
  display: block;
  opacity: 0;
  height: 0;
  margin: 0;
}

.xr-section-item > input + label,
.xr-var-item > input + label {
  color: var(--xr-disabled-color);
}

.xr-section-item > input:enabled + label,
.xr-var-item > input:enabled + label,
.xr-array-wrap > input:enabled + label,
.xr-group-box-contents > input:enabled + label {
  cursor: pointer;
  color: var(--xr-font-color2);
}

.xr-section-item > input:focus-visible + label,
.xr-var-item > input:focus-visible + label,
.xr-array-wrap > input:focus-visible + label,
.xr-group-box-contents > input:focus-visible + label {
  outline: auto;
}

.xr-section-item > input:enabled + label:hover,
.xr-var-item > input:enabled + label:hover,
.xr-array-wrap > input:enabled + label:hover,
.xr-group-box-contents > input:enabled + label:hover {
  color: var(--xr-font-color0);
}

.xr-section-summary {
  grid-column: 1;
  color: var(--xr-font-color2);
  font-weight: 500;
  white-space: nowrap;
}

.xr-section-summary > em {
  font-weight: normal;
}

.xr-span-grid {
  grid-column-end: -1;
}

.xr-section-summary > span {
  display: inline-block;
  padding-left: 0.3em;
}

.xr-group-box-contents > input:checked + label > span {
  display: inline-block;
  padding-left: 0.6em;
}

.xr-section-summary-in:disabled + label {
  color: var(--xr-font-color2);
}

.xr-section-summary-in + label:before {
  display: inline-block;
  content: "►";
  font-size: 11px;
  width: 15px;
  text-align: center;
}

.xr-section-summary-in:disabled + label:before {
  color: var(--xr-disabled-color);
}

.xr-section-summary-in:checked + label:before {
  content: "▼";
}

.xr-section-summary-in:checked + label > span {
  display: none;
}

.xr-section-summary,
.xr-section-inline-details,
.xr-group-box-contents > label {
  padding-top: 4px;
}

.xr-section-inline-details {
  grid-column: 2 / -1;
}

.xr-section-details {
  grid-column: 1 / -1;
  margin-top: 4px;
  margin-bottom: 5px;
}

.xr-section-summary-in ~ .xr-section-details {
  display: none;
}

.xr-section-summary-in:checked ~ .xr-section-details {
  display: contents;
}

.xr-children {
  display: inline-grid;
  grid-template-columns: 100%;
  grid-column: 1 / -1;
  padding-top: 4px;
}

.xr-group-box {
  display: inline-grid;
  grid-template-columns: 0px 30px auto;
}

.xr-group-box-vline {
  grid-column-start: 1;
  border-right: 0.2em solid;
  border-color: var(--xr-border-color);
  width: 0px;
}

.xr-group-box-hline {
  grid-column-start: 2;
  grid-row-start: 1;
  height: 1em;
  width: 26px;
  border-bottom: 0.2em solid;
  border-color: var(--xr-border-color);
}

.xr-group-box-contents {
  grid-column-start: 3;
  padding-bottom: 4px;
}

.xr-group-box-contents > label::before {
  content: "📂";
  padding-right: 0.3em;
}

.xr-group-box-contents > input:checked + label::before {
  content: "📁";
}

.xr-group-box-contents > input:checked + label {
  padding-bottom: 0px;
}

.xr-group-box-contents > input:checked ~ .xr-sections {
  display: none;
}

.xr-group-box-contents > input + label > span {
  display: none;
}

.xr-group-box-ellipsis {
  font-size: 1.4em;
  font-weight: 900;
  color: var(--xr-font-color2);
  letter-spacing: 0.15em;
  cursor: default;
}

.xr-array-wrap {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: 20px auto;
}

.xr-array-wrap > label {
  grid-column: 1;
  vertical-align: top;
}

.xr-preview {
  color: var(--xr-font-color3);
}

.xr-array-preview,
.xr-array-data {
  padding: 0 5px !important;
  grid-column: 2;
}

.xr-array-data,
.xr-array-in:checked ~ .xr-array-preview {
  display: none;
}

.xr-array-in:checked ~ .xr-array-data,
.xr-array-preview {
  display: inline-block;
}

.xr-dim-list {
  display: inline-block !important;
  list-style: none;
  padding: 0 !important;
  margin: 0;
}

.xr-dim-list li {
  display: inline-block;
  padding: 0;
  margin: 0;
}

.xr-dim-list:before {
  content: "(";
}

.xr-dim-list:after {
  content: ")";
}

.xr-dim-list li:not(:last-child):after {
  content: ",";
  padding-right: 5px;
}

.xr-has-index {
  font-weight: bold;
}

.xr-var-list,
.xr-var-item {
  display: contents;
}

.xr-var-item > div,
.xr-var-item label,
.xr-var-item > .xr-var-name span {
  background-color: var(--xr-background-color-row-even);
  border-color: var(--xr-background-color-row-odd);
  margin-bottom: 0;
  padding-top: 2px;
}

.xr-var-item > .xr-var-name:hover span {
  padding-right: 5px;
}

.xr-var-list > li:nth-child(odd) > div,
.xr-var-list > li:nth-child(odd) > label,
.xr-var-list > li:nth-child(odd) > .xr-var-name span {
  background-color: var(--xr-background-color-row-odd);
  border-color: var(--xr-background-color-row-even);
}

.xr-var-name {
  grid-column: 1;
}

.xr-var-dims {
  grid-column: 2;
}

.xr-var-dtype {
  grid-column: 3;
  text-align: right;
  color: var(--xr-font-color2);
}

.xr-var-preview {
  grid-column: 4;
}

.xr-index-preview {
  grid-column: 2 / 5;
  color: var(--xr-font-color2);
}

.xr-var-name,
.xr-var-dims,
.xr-var-dtype,
.xr-preview,
.xr-attrs dt {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding-right: 10px;
}

.xr-var-name:hover,
.xr-var-dims:hover,
.xr-var-dtype:hover,
.xr-attrs dt:hover {
  overflow: visible;
  width: auto;
  z-index: 1;
}

.xr-var-attrs,
.xr-var-data,
.xr-index-data {
  display: none;
  border-top: 2px dotted var(--xr-background-color);
  padding-bottom: 20px !important;
  padding-top: 10px !important;
}

.xr-var-attrs-in + label,
.xr-var-data-in + label,
.xr-index-data-in + label {
  padding: 0 1px;
}

.xr-var-attrs-in:checked ~ .xr-var-attrs,
.xr-var-data-in:checked ~ .xr-var-data,
.xr-index-data-in:checked ~ .xr-index-data {
  display: block;
}

.xr-var-data > table {
  float: right;
}

.xr-var-data > pre,
.xr-index-data > pre,
.xr-var-data > table > tbody > tr {
  background-color: transparent !important;
}

.xr-var-name span,
.xr-var-data,
.xr-index-name div,
.xr-index-data,
.xr-attrs {
  padding-left: 25px !important;
}

.xr-attrs,
.xr-var-attrs,
.xr-var-data,
.xr-index-data {
  grid-column: 1 / -1;
}

dl.xr-attrs {
  padding: 0;
  margin: 0;
  display: grid;
  grid-template-columns: 125px auto;
}

.xr-attrs dt,
.xr-attrs dd {
  padding: 0;
  margin: 0;
  float: left;
  padding-right: 10px;
  width: auto;
}

.xr-attrs dt {
  font-weight: normal;
  grid-column: 1;
}

.xr-attrs dt:hover span {
  display: inline-block;
  background: var(--xr-background-color);
  padding-right: 10px;
}

.xr-attrs dd {
  grid-column: 2;
  white-space: pre-wrap;
  word-break: break-all;
}

.xr-icon-database,
.xr-icon-file-text2,
.xr-no-icon {
  display: inline-block;
  vertical-align: middle;
  width: 1em;
  height: 1.5em !important;
  stroke-width: 0;
  stroke: currentColor;
  fill: currentColor;
}

.xr-var-attrs-in:checked + label > .xr-icon-file-text2,
.xr-var-data-in:checked + label > .xr-icon-database,
.xr-index-data-in:checked + label > .xr-icon-database {
  color: var(--xr-font-color0);
  filter: drop-shadow(1px 1px 5px var(--xr-font-color2));
  stroke-width: 0.8px;
}
</style><pre class='xr-text-repr-fallback'><xarray.Dataset> Size: 3kB
Dimensions:              (time: 90, site: 3)
Coordinates:
  * time                 (time) datetime64&#91;ns&#93; 720B 2020-01-01 ... 2020-03-30
  * site                 (site) <U1 12B 'a' 'b' 'c'
Data variables:
    temperature_anomaly  (time, site) float64 2kB -5.036 -5.036 ... -5.036
    anomaly_range        (site) float64 24B 7.999 7.999 7.999
Attributes:
    units:      degC
    long_name:  near-surface air temperature</pre><div class='xr-wrap' style='display:none'><div class='xr-header'><div class='xr-obj-type'>xarray.Dataset</div></div><ul class='xr-sections'><li class='xr-section-item'><input id='section-fb2a9ff7-02b9-4805-9242-2361f48aac19' class='xr-section-summary-in' type='checkbox' disabled /><label for='section-fb2a9ff7-02b9-4805-9242-2361f48aac19' class='xr-section-summary'>Dimensions:</label><div class='xr-section-inline-details'><ul class='xr-dim-list'><li><span class='xr-has-index'>time</span>: 90</li><li><span class='xr-has-index'>site</span>: 3</li></ul></div></li><li class='xr-section-item'><input id='section-f13d36bb-c89c-4f83-8f28-8115d479beeb' class='xr-section-summary-in' type='checkbox' checked /><label for='section-f13d36bb-c89c-4f83-8f28-8115d479beeb' class='xr-section-summary' title='Expand/collapse section'>Coordinates: <span>(2)</span></label><div class='xr-section-inline-details'></div><div class='xr-section-details'><ul class='xr-var-list'><li class='xr-var-item'><div class='xr-var-name'><span class='xr-has-index'>time</span></div><div class='xr-var-dims'>(time)</div><div class='xr-var-dtype'>datetime64&#91;ns&#93;</div><div class='xr-var-preview xr-preview'>2020-01-01 ... 2020-03-30</div><input id='attrs-98638280-45c0-41ce-a300-3654011f2bcb' class='xr-var-attrs-in' type='checkbox' disabled><label for='attrs-98638280-45c0-41ce-a300-3654011f2bcb' title='Show/Hide attributes'><svg class='icon xr-icon-file-text2'><use xlink:href='#icon-file-text2'></use></svg></label><input id='data-31449fa5-d244-48c6-81dd-047c654f7ac2' class='xr-var-data-in' type='checkbox'><label for='data-31449fa5-d244-48c6-81dd-047c654f7ac2' title='Show/Hide data repr'><svg class='icon xr-icon-database'><use xlink:href='#icon-database'></use></svg></label><div class='xr-var-attrs'><dl class='xr-attrs'></dl></div><div class='xr-var-data'><pre>array(&#91;'2020-01-01T00:00:00.000000000', '2020-01-02T00:00:00.000000000',
       '2020-01-03T00:00:00.000000000', '2020-01-04T00:00:00.000000000',
       '2020-01-05T00:00:00.000000000', '2020-01-06T00:00:00.000000000',
       '2020-01-07T00:00:00.000000000', '2020-01-08T00:00:00.000000000',
       '2020-01-09T00:00:00.000000000', '2020-01-10T00:00:00.000000000',
       '2020-01-11T00:00:00.000000000', '2020-01-12T00:00:00.000000000',
       '2020-01-13T00:00:00.000000000', '2020-01-14T00:00:00.000000000',
       '2020-01-15T00:00:00.000000000', '2020-01-16T00:00:00.000000000',
       '2020-01-17T00:00:00.000000000', '2020-01-18T00:00:00.000000000',
       '2020-01-19T00:00:00.000000000', '2020-01-20T00:00:00.000000000',
       '2020-01-21T00:00:00.000000000', '2020-01-22T00:00:00.000000000',
       '2020-01-23T00:00:00.000000000', '2020-01-24T00:00:00.000000000',
       '2020-01-25T00:00:00.000000000', '2020-01-26T00:00:00.000000000',
       '2020-01-27T00:00:00.000000000', '2020-01-28T00:00:00.000000000',
       '2020-01-29T00:00:00.000000000', '2020-01-30T00:00:00.000000000',
       '2020-01-31T00:00:00.000000000', '2020-02-01T00:00:00.000000000',
       '2020-02-02T00:00:00.000000000', '2020-02-03T00:00:00.000000000',
       '2020-02-04T00:00:00.000000000', '2020-02-05T00:00:00.000000000',
       '2020-02-06T00:00:00.000000000', '2020-02-07T00:00:00.000000000',
       '2020-02-08T00:00:00.000000000', '2020-02-09T00:00:00.000000000',
       '2020-02-10T00:00:00.000000000', '2020-02-11T00:00:00.000000000',
       '2020-02-12T00:00:00.000000000', '2020-02-13T00:00:00.000000000',
       '2020-02-14T00:00:00.000000000', '2020-02-15T00:00:00.000000000',
       '2020-02-16T00:00:00.000000000', '2020-02-17T00:00:00.000000000',
       '2020-02-18T00:00:00.000000000', '2020-02-19T00:00:00.000000000',
       '2020-02-20T00:00:00.000000000', '2020-02-21T00:00:00.000000000',
       '2020-02-22T00:00:00.000000000', '2020-02-23T00:00:00.000000000',
       '2020-02-24T00:00:00.000000000', '2020-02-25T00:00:00.000000000',
       '2020-02-26T00:00:00.000000000', '2020-02-27T00:00:00.000000000',
       '2020-02-28T00:00:00.000000000', '2020-02-29T00:00:00.000000000',
       '2020-03-01T00:00:00.000000000', '2020-03-02T00:00:00.000000000',
       '2020-03-03T00:00:00.000000000', '2020-03-04T00:00:00.000000000',
       '2020-03-05T00:00:00.000000000', '2020-03-06T00:00:00.000000000',
       '2020-03-07T00:00:00.000000000', '2020-03-08T00:00:00.000000000',
       '2020-03-09T00:00:00.000000000', '2020-03-10T00:00:00.000000000',
       '2020-03-11T00:00:00.000000000', '2020-03-12T00:00:00.000000000',
       '2020-03-13T00:00:00.000000000', '2020-03-14T00:00:00.000000000',
       '2020-03-15T00:00:00.000000000', '2020-03-16T00:00:00.000000000',
       '2020-03-17T00:00:00.000000000', '2020-03-18T00:00:00.000000000',
       '2020-03-19T00:00:00.000000000', '2020-03-20T00:00:00.000000000',
       '2020-03-21T00:00:00.000000000', '2020-03-22T00:00:00.000000000',
       '2020-03-23T00:00:00.000000000', '2020-03-24T00:00:00.000000000',
       '2020-03-25T00:00:00.000000000', '2020-03-26T00:00:00.000000000',
       '2020-03-27T00:00:00.000000000', '2020-03-28T00:00:00.000000000',
       '2020-03-29T00:00:00.000000000', '2020-03-30T00:00:00.000000000'&#93;,
      dtype='datetime64&#91;ns&#93;')</pre></div></li><li class='xr-var-item'><div class='xr-var-name'><span class='xr-has-index'>site</span></div><div class='xr-var-dims'>(site)</div><div class='xr-var-dtype'><U1</div><div class='xr-var-preview xr-preview'>'a' 'b' 'c'</div><input id='attrs-f6487be4-5c65-492a-b629-f91f5837bf27' class='xr-var-attrs-in' type='checkbox' disabled><label for='attrs-f6487be4-5c65-492a-b629-f91f5837bf27' title='Show/Hide attributes'><svg class='icon xr-icon-file-text2'><use xlink:href='#icon-file-text2'></use></svg></label><input id='data-c5b32eb9-9e8a-4927-b148-c08d884574e0' class='xr-var-data-in' type='checkbox'><label for='data-c5b32eb9-9e8a-4927-b148-c08d884574e0' title='Show/Hide data repr'><svg class='icon xr-icon-database'><use xlink:href='#icon-database'></use></svg></label><div class='xr-var-attrs'><dl class='xr-attrs'></dl></div><div class='xr-var-data'><pre>array(&#91;'a', 'b', 'c'&#93;, dtype='<U1')</pre></div></li></ul></div></li><li class='xr-section-item'><input id='section-53e64841-a73c-470c-808a-d78c62738839' class='xr-section-summary-in' type='checkbox' checked /><label for='section-53e64841-a73c-470c-808a-d78c62738839' class='xr-section-summary' title='Expand/collapse section'>Data variables: <span>(2)</span></label><div class='xr-section-inline-details'></div><div class='xr-section-details'><ul class='xr-var-list'><li class='xr-var-item'><div class='xr-var-name'><span>temperature_anomaly</span></div><div class='xr-var-dims'>(time, site)</div><div class='xr-var-dtype'>float64</div><div class='xr-var-preview xr-preview'>-5.036 -5.036 ... -5.036 -5.036</div><input id='attrs-8fac7eae-7ed4-4393-bfbd-a99505b5fb78' class='xr-var-attrs-in' type='checkbox' ><label for='attrs-8fac7eae-7ed4-4393-bfbd-a99505b5fb78' title='Show/Hide attributes'><svg class='icon xr-icon-file-text2'><use xlink:href='#icon-file-text2'></use></svg></label><input id='data-1435ef7e-dd9a-4825-8967-cf4a56536b2d' class='xr-var-data-in' type='checkbox'><label for='data-1435ef7e-dd9a-4825-8967-cf4a56536b2d' title='Show/Hide data repr'><svg class='icon xr-icon-database'><use xlink:href='#icon-database'></use></svg></label><div class='xr-var-attrs'><dl class='xr-attrs'><dt><span>units :</span></dt><dd>degC</dd><dt><span>long_name :</span></dt><dd>near-surface air temperature</dd></dl></div><div class='xr-var-data'><pre>array(&#91;&#91;-5.0358468 , -5.0358468 , -5.0358468 &#93;,
       &#91;-4.75351509, -4.75351509, -4.75351509&#93;,
       &#91;-4.47153513, -4.47153513, -4.47153513&#93;,
       &#91;-4.19025823, -4.19025823, -4.19025823&#93;,
       &#91;-3.91003483, -3.91003483, -3.91003483&#93;,
       &#91;-3.63121405, -3.63121405, -3.63121405&#93;,
       &#91;-3.35414327, -3.35414327, -3.35414327&#93;,
       &#91;-3.07916768, -3.07916768, -3.07916768&#93;,
       &#91;-2.80662987, -2.80662987, -2.80662987&#93;,
       &#91;-2.53686938, -2.53686938, -2.53686938&#93;,
       &#91;-2.27022231, -2.27022231, -2.27022231&#93;,
       &#91;-2.00702087, -2.00702087, -2.00702087&#93;,
       &#91;-1.74759296, -1.74759296, -1.74759296&#93;,
       &#91;-1.49226181, -1.49226181, -1.49226181&#93;,
       &#91;-1.24134553, -1.24134553, -1.24134553&#93;,
       &#91;-0.99515672, -0.99515672, -0.99515672&#93;,
       &#91;-0.75400211, -0.75400211, -0.75400211&#93;,
       &#91;-0.51818214, -0.51818214, -0.51818214&#93;,
       &#91;-0.28799062, -0.28799062, -0.28799062&#93;,
       &#91;-0.06371434, -0.06371434, -0.06371434&#93;,
...
       &#91;-0.06371434, -0.06371434, -0.06371434&#93;,
       &#91;-0.28799062, -0.28799062, -0.28799062&#93;,
       &#91;-0.51818214, -0.51818214, -0.51818214&#93;,
       &#91;-0.75400211, -0.75400211, -0.75400211&#93;,
       &#91;-0.99515672, -0.99515672, -0.99515672&#93;,
       &#91;-1.24134553, -1.24134553, -1.24134553&#93;,
       &#91;-1.49226181, -1.49226181, -1.49226181&#93;,
       &#91;-1.74759296, -1.74759296, -1.74759296&#93;,
       &#91;-2.00702087, -2.00702087, -2.00702087&#93;,
       &#91;-2.27022231, -2.27022231, -2.27022231&#93;,
       &#91;-2.53686938, -2.53686938, -2.53686938&#93;,
       &#91;-2.80662987, -2.80662987, -2.80662987&#93;,
       &#91;-3.07916768, -3.07916768, -3.07916768&#93;,
       &#91;-3.35414327, -3.35414327, -3.35414327&#93;,
       &#91;-3.63121405, -3.63121405, -3.63121405&#93;,
       &#91;-3.91003483, -3.91003483, -3.91003483&#93;,
       &#91;-4.19025823, -4.19025823, -4.19025823&#93;,
       &#91;-4.47153513, -4.47153513, -4.47153513&#93;,
       &#91;-4.75351509, -4.75351509, -4.75351509&#93;,
       &#91;-5.0358468 , -5.0358468 , -5.0358468 &#93;&#93;)</pre></div></li><li class='xr-var-item'><div class='xr-var-name'><span>anomaly_range</span></div><div class='xr-var-dims'>(site)</div><div class='xr-var-dtype'>float64</div><div class='xr-var-preview xr-preview'>7.999 7.999 7.999</div><input id='attrs-2840a30d-777f-4be9-8626-8b4044a2f724' class='xr-var-attrs-in' type='checkbox' ><label for='attrs-2840a30d-777f-4be9-8626-8b4044a2f724' title='Show/Hide attributes'><svg class='icon xr-icon-file-text2'><use xlink:href='#icon-file-text2'></use></svg></label><input id='data-f6f23c26-e396-4ccf-b5c5-bfc913ce2241' class='xr-var-data-in' type='checkbox'><label for='data-f6f23c26-e396-4ccf-b5c5-bfc913ce2241' title='Show/Hide data repr'><svg class='icon xr-icon-database'><use xlink:href='#icon-database'></use></svg></label><div class='xr-var-attrs'><dl class='xr-attrs'><dt><span>units :</span></dt><dd>degC</dd><dt><span>long_name :</span></dt><dd>near-surface air temperature</dd></dl></div><div class='xr-var-data'><pre>array(&#91;7.99875403, 7.99875403, 7.99875403&#93;)</pre></div></li></ul></div></li><li class='xr-section-item'><input id='section-f9c3235a-d7f7-4445-a384-0e43f3c80969' class='xr-section-summary-in' type='checkbox' checked /><label for='section-f9c3235a-d7f7-4445-a384-0e43f3c80969' class='xr-section-summary' title='Expand/collapse section'>Attributes: <span>(2)</span></label><div class='xr-section-inline-details'></div><div class='xr-section-details'><dl class='xr-attrs'><dt><span>units :</span></dt><dd>degC</dd><dt><span>long_name :</span></dt><dd>near-surface air temperature</dd></dl></div></li></ul></div></div>