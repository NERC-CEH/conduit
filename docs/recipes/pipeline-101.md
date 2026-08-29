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
mo.Html(graph.pipe(format="svg").decode())
```

<!-- @output:SFPL -->

<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN"
 "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">
<!-- Generated by graphviz version 2.43.0 (0)
 -->
<!-- Title: %3 Pages: 1 -->
<svg width="823pt" height="271pt"
 viewBox="0.00 0.00 823.00 271.00" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
<g id="graph0" class="graph" transform="scale(1 1) rotate(0) translate(4 267)">
<title>%3</title>
<polygon fill="white" stroke="transparent" points="-4,4 -4,-267 819,-267 819,4 -4,4"/>
<g id="clust1" class="cluster">
<title>cluster__legend</title>
<polygon fill="#ffffff" stroke="black" points="103.5,-123 103.5,-255 187.5,-255 187.5,-123 103.5,-123"/>
<text text-anchor="middle" x="145.5" y="-239.8" font-family="Helvetica,sans-Serif" font-size="14.00">Legend</text>
</g>
<!-- hamilton.enable_power_user_mode -->
<g id="node1" class="node">
<title>hamilton.enable_power_user_mode</title>
<polygon fill="#ffffff" stroke="black" points="285,-50 0,-50 0,0 291,0 291,-44 285,-50"/>
<polyline fill="none" stroke="black" points="285,-50 285,-44 "/>
<polyline fill="none" stroke="black" points="291,-44 285,-44 "/>
<text text-anchor="start" x="8" y="-35.8" font-family="Helvetica,sans-Serif" font-weight="bold" font-size="14.00">hamilton.enable_power_user_mode</text>
<text text-anchor="start" x="130" y="-7.8" font-family="Helvetica,sans-Serif" font-style="italic" font-size="14.00">True</text>
</g>
<!-- anomaly_range_climate -->
<g id="node2" class="node">
<title>anomaly_range_climate</title>
<path fill="#b4d8e4" stroke="#e7298a" stroke-width="2.5" d="M803,-123C803,-123 621,-123 621,-123 615,-123 609,-117 609,-111 609,-111 609,-71 609,-71 609,-65 615,-59 621,-59 621,-59 803,-59 803,-59 809,-59 815,-65 815,-71 815,-71 815,-111 815,-111 815,-117 809,-123 803,-123"/>
<text text-anchor="start" x="620" y="-101.8" font-family="Helvetica,sans-Serif" font-weight="bold" font-size="14.00">anomaly_range_climate</text>
<text text-anchor="start" x="693.5" y="-73.8" font-family="Helvetica,sans-Serif" font-style="italic" font-size="14.00">degC</text>
</g>
<!-- temperature_anomaly_climate -->
<g id="node3" class="node">
<title>temperature_anomaly_climate</title>
<path fill="#b4d8e4" stroke="#e7298a" stroke-width="2.5" d="M568,-123C568,-123 332,-123 332,-123 326,-123 320,-117 320,-111 320,-111 320,-71 320,-71 320,-65 326,-59 332,-59 332,-59 568,-59 568,-59 574,-59 580,-65 580,-71 580,-71 580,-111 580,-111 580,-117 574,-123 568,-123"/>
<text text-anchor="start" x="331" y="-101.8" font-family="Helvetica,sans-Serif" font-weight="bold" font-size="14.00">temperature_anomaly_climate</text>
<text text-anchor="start" x="431.5" y="-73.8" font-family="Helvetica,sans-Serif" font-style="italic" font-size="14.00">degC</text>
</g>
<!-- temperature_anomaly_climate->anomaly_range_climate -->
<g id="edge1" class="edge">
<title>temperature_anomaly_climate->anomaly_range_climate</title>
<path fill="none" stroke="black" d="M580.24,-91C586.36,-91 592.49,-91 598.56,-91"/>
<polygon fill="black" stroke="black" points="598.72,-94.5 608.72,-91 598.72,-87.5 598.72,-94.5"/>
</g>
<!-- _temperature_anomaly_climate_inputs -->
<g id="node4" class="node">
<title>_temperature_anomaly_climate_inputs</title>
<polygon fill="#ffffff" stroke="black" stroke-dasharray="5,2" points="254,-113.5 37,-113.5 37,-68.5 254,-68.5 254,-113.5"/>
<text text-anchor="start" x="52.5" y="-86.8" font-family="Helvetica,sans-Serif" font-size="14.00">temperature_climate</text>
<text text-anchor="start" x="202.5" y="-86.8" font-family="Helvetica,sans-Serif" font-size="14.00">degC</text>
</g>
<!-- _temperature_anomaly_climate_inputs->temperature_anomaly_climate -->
<g id="edge2" class="edge">
<title>_temperature_anomaly_climate_inputs->temperature_anomaly_climate</title>
<path fill="none" stroke="black" d="M254,-91C272.07,-91 291.04,-91 309.77,-91"/>
<polygon fill="black" stroke="black" points="309.84,-94.5 319.84,-91 309.84,-87.5 309.84,-94.5"/>
</g>
<!-- input -->
<g id="node5" class="node">
<title>input</title>
<polygon fill="#ffffff" stroke="black" stroke-dasharray="5,2" points="175,-223.5 116,-223.5 116,-186.5 175,-186.5 175,-223.5"/>
<text text-anchor="middle" x="145.5" y="-201.3" font-family="Helvetica,sans-Serif" font-size="14.00">input</text>
</g>
<!-- output -->
<g id="node6" class="node">
<title>output</title>
<path fill="#b4d8e4" stroke="#e7298a" stroke-width="2.5" d="M167.5,-168.5C167.5,-168.5 123.5,-168.5 123.5,-168.5 117.5,-168.5 111.5,-162.5 111.5,-156.5 111.5,-156.5 111.5,-143.5 111.5,-143.5 111.5,-137.5 117.5,-131.5 123.5,-131.5 123.5,-131.5 167.5,-131.5 167.5,-131.5 173.5,-131.5 179.5,-137.5 179.5,-143.5 179.5,-143.5 179.5,-156.5 179.5,-156.5 179.5,-162.5 173.5,-168.5 167.5,-168.5"/>
<text text-anchor="middle" x="145.5" y="-146.3" font-family="Helvetica,sans-Serif" font-size="14.00">output</text>
</g>
</g>
</svg>

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
    long_name:  near-surface air temperature</pre><div class='xr-wrap' style='display:none'><div class='xr-header'><div class='xr-obj-type'>xarray.Dataset</div></div><ul class='xr-sections'><li class='xr-section-item'><input id='section-7daab35f-bc48-498e-836a-c2e4fe3e2f9f' class='xr-section-summary-in' type='checkbox' disabled /><label for='section-7daab35f-bc48-498e-836a-c2e4fe3e2f9f' class='xr-section-summary'>Dimensions:</label><div class='xr-section-inline-details'><ul class='xr-dim-list'><li><span class='xr-has-index'>time</span>: 90</li><li><span class='xr-has-index'>site</span>: 3</li></ul></div></li><li class='xr-section-item'><input id='section-6b26ba25-6cc2-4d86-a77d-dfe575851fe4' class='xr-section-summary-in' type='checkbox' checked /><label for='section-6b26ba25-6cc2-4d86-a77d-dfe575851fe4' class='xr-section-summary' title='Expand/collapse section'>Coordinates: <span>(2)</span></label><div class='xr-section-inline-details'></div><div class='xr-section-details'><ul class='xr-var-list'><li class='xr-var-item'><div class='xr-var-name'><span class='xr-has-index'>time</span></div><div class='xr-var-dims'>(time)</div><div class='xr-var-dtype'>datetime64&#91;ns&#93;</div><div class='xr-var-preview xr-preview'>2020-01-01 ... 2020-03-30</div><input id='attrs-438dd63e-c035-4a0e-9078-30489838d990' class='xr-var-attrs-in' type='checkbox' disabled><label for='attrs-438dd63e-c035-4a0e-9078-30489838d990' title='Show/Hide attributes'><svg class='icon xr-icon-file-text2'><use xlink:href='#icon-file-text2'></use></svg></label><input id='data-ac476e87-d9b2-4374-b9e8-1c728a3cf65f' class='xr-var-data-in' type='checkbox'><label for='data-ac476e87-d9b2-4374-b9e8-1c728a3cf65f' title='Show/Hide data repr'><svg class='icon xr-icon-database'><use xlink:href='#icon-database'></use></svg></label><div class='xr-var-attrs'><dl class='xr-attrs'></dl></div><div class='xr-var-data'><pre>array(&#91;'2020-01-01T00:00:00.000000000', '2020-01-02T00:00:00.000000000',
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
      dtype='datetime64&#91;ns&#93;')</pre></div></li><li class='xr-var-item'><div class='xr-var-name'><span class='xr-has-index'>site</span></div><div class='xr-var-dims'>(site)</div><div class='xr-var-dtype'><U1</div><div class='xr-var-preview xr-preview'>'a' 'b' 'c'</div><input id='attrs-2c8720e7-79b6-4095-ba27-c99ec459663c' class='xr-var-attrs-in' type='checkbox' disabled><label for='attrs-2c8720e7-79b6-4095-ba27-c99ec459663c' title='Show/Hide attributes'><svg class='icon xr-icon-file-text2'><use xlink:href='#icon-file-text2'></use></svg></label><input id='data-dc5d96e1-744e-4c2a-9763-2e4e5a165cbf' class='xr-var-data-in' type='checkbox'><label for='data-dc5d96e1-744e-4c2a-9763-2e4e5a165cbf' title='Show/Hide data repr'><svg class='icon xr-icon-database'><use xlink:href='#icon-database'></use></svg></label><div class='xr-var-attrs'><dl class='xr-attrs'></dl></div><div class='xr-var-data'><pre>array(&#91;'a', 'b', 'c'&#93;, dtype='<U1')</pre></div></li></ul></div></li><li class='xr-section-item'><input id='section-fc9bea89-3349-47b2-ac0f-e6a28c37a2e4' class='xr-section-summary-in' type='checkbox' checked /><label for='section-fc9bea89-3349-47b2-ac0f-e6a28c37a2e4' class='xr-section-summary' title='Expand/collapse section'>Data variables: <span>(2)</span></label><div class='xr-section-inline-details'></div><div class='xr-section-details'><ul class='xr-var-list'><li class='xr-var-item'><div class='xr-var-name'><span>temperature_anomaly</span></div><div class='xr-var-dims'>(time, site)</div><div class='xr-var-dtype'>float64</div><div class='xr-var-preview xr-preview'>-5.036 -5.036 ... -5.036 -5.036</div><input id='attrs-49072d62-0705-49a2-9d77-acdce79f0556' class='xr-var-attrs-in' type='checkbox' ><label for='attrs-49072d62-0705-49a2-9d77-acdce79f0556' title='Show/Hide attributes'><svg class='icon xr-icon-file-text2'><use xlink:href='#icon-file-text2'></use></svg></label><input id='data-490e4e37-ce02-484a-b656-d6e628b0d8b3' class='xr-var-data-in' type='checkbox'><label for='data-490e4e37-ce02-484a-b656-d6e628b0d8b3' title='Show/Hide data repr'><svg class='icon xr-icon-database'><use xlink:href='#icon-database'></use></svg></label><div class='xr-var-attrs'><dl class='xr-attrs'><dt><span>units :</span></dt><dd>degC</dd><dt><span>long_name :</span></dt><dd>near-surface air temperature</dd></dl></div><div class='xr-var-data'><pre>array(&#91;&#91;-5.0358468 , -5.0358468 , -5.0358468 &#93;,
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
       &#91;-5.0358468 , -5.0358468 , -5.0358468 &#93;&#93;)</pre></div></li><li class='xr-var-item'><div class='xr-var-name'><span>anomaly_range</span></div><div class='xr-var-dims'>(site)</div><div class='xr-var-dtype'>float64</div><div class='xr-var-preview xr-preview'>7.999 7.999 7.999</div><input id='attrs-3ee1d7dd-0caf-4ef7-91e4-1cf56e3e65f2' class='xr-var-attrs-in' type='checkbox' ><label for='attrs-3ee1d7dd-0caf-4ef7-91e4-1cf56e3e65f2' title='Show/Hide attributes'><svg class='icon xr-icon-file-text2'><use xlink:href='#icon-file-text2'></use></svg></label><input id='data-fa740cc5-3977-4926-9add-07a2cd888db3' class='xr-var-data-in' type='checkbox'><label for='data-fa740cc5-3977-4926-9add-07a2cd888db3' title='Show/Hide data repr'><svg class='icon xr-icon-database'><use xlink:href='#icon-database'></use></svg></label><div class='xr-var-attrs'><dl class='xr-attrs'><dt><span>units :</span></dt><dd>degC</dd><dt><span>long_name :</span></dt><dd>near-surface air temperature</dd></dl></div><div class='xr-var-data'><pre>array(&#91;7.99875403, 7.99875403, 7.99875403&#93;)</pre></div></li></ul></div></li><li class='xr-section-item'><input id='section-f953df2c-18f0-42f7-b9a0-17c023ba616b' class='xr-section-summary-in' type='checkbox' checked /><label for='section-f953df2c-18f0-42f7-b9a0-17c023ba616b' class='xr-section-summary' title='Expand/collapse section'>Attributes: <span>(2)</span></label><div class='xr-section-inline-details'></div><div class='xr-section-details'><dl class='xr-attrs'><dt><span>units :</span></dt><dd>degC</dd><dt><span>long_name :</span></dt><dd>near-surface air temperature</dd></dl></div></li></ul></div></div>