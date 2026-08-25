---
title: 'conduit: pipeline 101'
marimo-version: 0.23.14

  """Executable walkthrough of the smallest complete conduit pipeline."""
---

```python {.marimo}
import subprocess

import marimo as mo
import xarray as xr
from xarray_annotated.units import use_cf_units

use_cf_units()
```

# Pipeline 101

The smallest pipeline that still has every moving part: an input file, a
node function imported from a Python module, a node defined inline in the
config, and an output file.

It derives a temperature anomaly from 90 days of daily temperature at three
sites, then reduces the anomaly to a per-site range.

```python {.marimo}
from pathlib import Path

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

```python {.marimo}
def conduit(*args):
    """Run the conduit CLI from the repository root, with absolute paths scrubbed.

    cwd is the repository root, which conduit appends to sys.path, so
    `_import_path = "recipes.pipeline_101.nodes"` resolves.
    """
    proc = subprocess.run(
        ["conduit", *args],
        check=True,
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    for stream in (proc.stdout, proc.stderr):
        if stream:
            print(stream.replace(f"{project_dir}/", ""), end="")
```

## The input

`make_data.py` writes a deterministic NetCDF file next to this notebook. The
`units` attribute on the variable is what lets conduit check the pipeline's
unit contracts against the file before running anything.

```python {.marimo}
import sys

# make_data.py sits next to this notebook, which is not necessarily importable.
sys.path.insert(0, str(recipe_dir))
from make_data import write_inputs

rel(write_inputs(data_dir))
```

<!-- @output:PKri -->

<pre style="white-space: pre-wrap; overflow-wrap: break-word;">PosixPath(&#x27;recipes/pipeline_101/data/climate.nc&#x27;)</pre>

<!-- @output:Xref -->

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

<!-- @output:SFPL -->

<span class="markdown prose dark:prose-invert contents"><h2 id="the-config">The config</h2>
<span class="paragraph">Three kinds of section, and between them they describe the whole graph.</span>
<div class="language-toml codehilite"><pre><span></span><code><span class="c1"># The smallest pipeline that still has every moving part: an input file, an</span>
<span class="c1"># imported node function, an inline node, and an output file.</span>

<span class="k">&#91;inputs.climate&#93;</span>
<span class="n">path</span><span class="w"> </span><span class="o">=</span><span class="w"> </span><span class="s2">"data/climate.nc"</span>
<span class="n">vars</span><span class="w"> </span><span class="o">=</span><span class="w"> </span><span class="p">&#91;</span><span class="s2">"temperature"</span><span class="p">&#93;</span>

<span class="c1"># Any section conduit does not recognise is one of your own modules, and must</span>
<span class="c1"># say where to import it from.</span>
<span class="k">&#91;climate_nodes&#93;</span>
<span class="n">_import_path</span><span class="w"> </span><span class="o">=</span><span class="w"> </span><span class="s2">"recipes.pipeline_101.nodes"</span>

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

```python {.marimo}
graph_base = recipe_dir / "pipeline"
conduit("graph", str(rel(config_path)), "--output", str(rel(graph_base)), "--png")
graph_path = graph_base.with_suffix(".png")
```

<!-- @output:BYtC -->

<pre style="white-space: pre-wrap; overflow-wrap: break-word;">Wrote recipes/pipeline_101/pipeline.dot
Wrote recipes/pipeline_101/pipeline.png
</pre>

## The graph conduit builds

`conduit graph` renders the DAG without running it. Node labels carry the
declared units, so a wiring mistake is often visible before a dry run
reports it.

```python {.marimo}
mo.image(graph_path, alt="Graphviz graph of the pipeline", width="100%")
```

<!-- @output:Kclp -->

<img src='data:image/png;base64,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AcpM+d+xP5u9aM1vCw9FR12Pu2Q0Gd2qVmvUsnWvoCFNn3xK6dAqEXIboLJjro6KqPcLQ3u/wAiHO1afiFM6BOW5elQtfDuwlVARVaAdu6aPr3kql9IoP2tUEVWAedIAAAAA4KHIbaCAffv2SZL0ySef3PdlhTZ//nxJkiIjIx9F4xs3bnzhhRe8vb11Op27u3uLFi1Gjhy5adMmo9H4KLoDAACoWCpAbhMWFubv7//w5R4sKipKkqRJkyaVVUjlVuVZ0xKo0BsnKytr6NChAQEBYWFhly5dysrKSkhIOHz48Pz587t3775z506lAwQAAFBeBbjfhifbqF6bNm3K/3OWlDV27NhFixYZDIb3338/MDCwbt26mZmZly5diomJWbBggaZcToUJAABgZRUgtwEquX379s2ePVuv12/btq1169ZypU6nc3Fxadas2dCh3FBemIMHD3722WeDBw9+/vnn9fpyOrUOALXKzMzs3bv34MGDAwMD3dzclA4HUL8KMCatlCZNmtShQwchxMcffyz9Q37LZDLNnTvX39/fyclJr9e3aNFi+vTp5gsI69atkyRp2rRpW7Zs8ff3NxgMtWrV+vrrr+V3f/jhh4YNG+p0ukaNGkVERJi7M39q06ZN/v7+Dg4O1apVGz16dHx8vGVURex627ZtnTp1cnJyatOmjfzW9u3bX3rpJV9fX3t7+6pVqz7//PN//fVX4Ws6e/bse+8AkStXrFhReI+Fx1k4k8k0f/78jh07uri4ODk5Pfnkk7NmzcrNzb13yQL325Rsy5ds45RyHZOSksaOHevl5aXX69u0abN69er7bofC209MTHzjjTeqV69ubqTATTvz5s0TQrz99tvmxAZFl52dvWLFiuDgYHd395deemnNmjX33QkB4FEwmUxbt24dM2aMp6dn7969f/3117S0NKWDAtSs8l63MZlMQ4cOXbx4sbnm8OHDY8eOPXTo0M8//2yu3LVr17vvviufDKWnp3/wwQf29vbXrl2bPHmyvMDJkydfeOGF+vXrt2zZ0vypnTt3vvPOO3l5eUKIjIyM2bNnR0VF7d2719HRsehd79y509y1fLP4tWvXOnXqZF7g5s2bq1evXrdu3aZNmzp27Fj6bVKgxyLGeV8mk2nw4MFhYWHmmn379u3bt69u3brdu3cvSjDF3fIl2zilWcfMzMwuXbrExMTIL/fv39+nT58CQygf2n5mZmbXrl0Lb0S+nWbAgAGFx1NiISEhj6jlciUjIyMiImLJkiWOjo79+/cfNmxY165dbWzU//sOgPIgNzd3w4YN69ev12g0AQEBI0aM6Nu3r52dndJxAWqj/r/rEydO3LFjhxDi888/N/1DCLFo0aLFixc3a9ZszZo1t27dSk1N3bZtW4sWLWbNmmX5uI+wsLCxY8eeP38+NTU1MjJSq9V++umnM2fOnD179o0bN27duhUSEmI0GqdOnWrZaURExNChQ0+fPp2amrp9+/ZmzZqdOHHim2++kd8tYtcRERHDhg07efJkbm7ugQMHhBCSJAUEBPz++++XLl3Kzs6+fv16eHi4vb29fE3jQWtadAV6LGKc9zV37tywsDB3d/effvrp4sWLqampe/fufeWVV7RabRGDKe6WL9nGKc06/vDDDzExMQ0bNty4cWNKSsrZs2dff/11y3SuKO2bG9m0aVNKSsq5c+fGjh1boJFr164JIerWrVvETVdcfn5+fn5+j6jxciUnJ0cIkZqaGhYWFhAQUL169bfffjsqKkrpuABUCnl5eUajMScnZ8OGDcHBwW5ubkOHDv3999+5mAyUIfXnNg8yb948jUbz559/9u7d283NzWAwdOzYccmSJUKIlStXmhfr1avX1KlTa9eubTAYBg4c2KdPn9u3b3/yySejRo2qWrWqm5vbN9984+zsfOzYMcvG27ZtO3fuXF9fX4PB0KFDhxUrVmi1WsshRkXp2s/Pb/bs2Q0aNDDfKe7p6fnVV18tWLDgqaeecnBw8PT0DAoKSktL+/vvv8tkmxTosYhx3tcvv/wihPjtt9/GjBlTq1Ytg8HQpk2bWbNmWV5aKVxxt3zJNk5p1nHp0qWSJC1durRbt26Ojo5169adPn16t27ditV+ZGSk3EjXrl0dHR3r1Knz/fffBwQEFHEroWSys7OFEPHx8T/99FOHDh18fX2/3vXr2ez4h34QAEovJyfHZDKlpaWFh4f36dPnsccee+enL/aknzcJptUBSqvyjkk7evRoXl5erVq1hBDmX/Hl/7148aJ5sQLn4rVr1xZCWI5x0mg0NWrUuH79uuViPXr0MN/OIYTw8fFp0KDBqVOnitV19+7dLRsRQuzcubNLly7yaZmljIyM4q7+fRXosYhx3teJEydcXV2LOPzsvoq75Uu2cUqzjrGxsTVq1GjSpIllZa9evTZt2lT09s+cOXNvIz179tywYYP5ZfXq1a9du3bu3DkPD4/CQyoxGxubyjlVnbzDnDlz5pszZ74R4gm9d0i9V5zF00rHBUBhuSZjrRP/Fr3fe6S9mH9nmb5y4XQhfOyqvl+1Rw3x4iPtFFC3CpDbBAUFjR8/vl27dmXbrHwHi3xLTAGW58c6nc7yLfnU/97KYj08sYhdu7u7F3j366+/zs7O/u9//zt06NAaNWrY29tLktSoUaObN28W0p18R0GBCO97xl+gxyLG+YgUd8uXbOM86nUsSvsFMljxT/Jj5u/vHxMTs3z58ieffLL0Id1XgVFwanL69OmPPvqokAW0Wm1OTo6va41B2ub9q7R09Gxw1mrBASivNJL0c40hhuFttC0fK0072dnZQ4YMKWQB+RBUzcV9kKZZ/yqtmui89pemP6DSqwC5TURERGBgYGlyG/nkvsB41kaNGh04cODKlSvOzs6lDfEe69ev/+yzz8znrGfPnj116lS9evVK2fXZs2c9PT3N84kJIc6cOXP69GlXV1f55X3XtFq1akKIc+fOWVZu3rz5od2VZhM1atRox44dmzZtKjBG69Ep2cYpzTr6+vru2bPn6NGjlldd1q1bV6z269Wrt3fv3mPHjjVu3NhcaXnRRggxcuTIGTNmfPfdd0FBQZZTVpShQYMGPYpmy4Pdu3ffN7exs7PLzs729PQMDg4eNmxYvUWXM/88KYRItHqEAMohSUjPV2nu0qGXrlfD0rTzoLEDtra2ubm5Tk5O/fr1GzZsWPucmrdDfi9NRwBkleJ+G3lG+R07dty6dctcOWrUqPT09O7du69evTo+Pj47O/vChQt//PHHwIEDLccUlcyePXtGjRoVGxublpYWFRXVv3//nJycwMDAUnbt7e1948aNH3/88fbt27dv316zZs0zzzxjeUHmvmsqnzRPmzZt69atGRkZ58+fDwkJMc/+XIjSbKLhw4cLIQYPHjxr1qy4uLi0tLT9+/e/+uqr27Zte2i/JVOyjVOadRw4cKDJZBo4cODmzZtTU1PPnTv35ptvFvjUQ9uXGwkMDNy6dWtaWtqFCxfGjx+/fv16y0batGnzyiuvpKend+jQ4Ysvvjhx4kRWVtbt27ePHDmycOHCHj16PHTaA5jZ2toKIZydnUeMGLFjx46rV69+9913TK4NwDo0Go2NjY2dnV3fvn1XrVp169atBQsW3DsEHUCJVYDrNqVXv379GjVqbN682Xy7gslkGj58+LZt2+bPn//8888XWH706NGl7DEwMHDBggXyY0lkjRo1ev/99+VyibseM2bM2rVr33rrrbfeekuuadWqVdOmTa9evSq/vO+a+vj4DBgwYNmyZV26dJErbW1thw4dunDhwsLXojSbaOTIkevWrYuMjHz11Vct6wvMblyGSrZxSrOOb7311pIlS2JiYszXpiRJCg4Othzf9dD233rrrcWLFx8+fNj8ryNJ0qBBgyIiIiznlPvxxx8zMjIWL148ceLEiRMnFmjqP//5T+GhQqPRGI1GvV4fGBg4ZMiQrl27mqfoAIBHTX6omo2NzTPPPDNkyJDnnnuORwkDj0iluG6j0WgiIyOffvppg8FgrpQkad68eWFhYd27d3d1dbWzs/Px8enXr9/y5ctLcwe8rH379mvXrm3btq1er/fw8Bg1atT27dvlh9uUpuu+ffsuXry4efPmer3ey8trzJgxmzZtsre3L3xNhRBz5sx5+eWX3d3ddTpdu3btNm7cWJTn4ZRmE9nY2ISHh//8889+fn4Gg6FKlSpt27adPXt2586dH9pvyZRs45RmHXU63ZYtW9544w1PT0+dTteqVavly5f36tXLcpmHtq/X67ds2TJmzJhq1arpdLrWrVuvWrVKvtRmHk0nhLC3t1+0aNH69euDg4Nr1aplZ2fn6urarFmzkSNHbtiwwd/fvzSbLjQ0NDQ0tDQtlHM6na5v375Lly69devWL7/8EhAQQGIDwGo0Gk2nTp1mz54dHx+/cuXKQYMGkdgAj45U/idHkiQpLCzs0f3eX7bWrVvXu3fvqVOnjhs3TulYUCEZjcY2bdrExMTEx8ffO5/EoyDfbBMREWGFvqwvJSXFZDJVqVKl8MWSxq/Kv9/G3/vsu8yTBlRqrfsvkQsuoX1Keb+N0Wi8ceNG9erVC18sc93JpAmr5PL+5cyTBhSJz7dRrjsvCiF0PRu6TO0jV1aK6zZAeRYSErJo0aILFy6kp6fHxMQEBQUdPHiwc+fO1klsVM/JyemhiQ0APCI2NjYPTWwAlKFKcb8NylxMTEyrVq0e9G7fvn2LMlcBZCdPniwwJMzR0VHdg8QAAAAehQpw3SYsLKyUtxMA5dnUqVNHjBjh6+trb29ftWrVwMDA6OjoRzTXMwAAgIpVgOs2FeVOG1mvXr3K/y1MpdeyZcvKsJrWUb9+fcsp9QA8Cl+9PWbnhrUR+47rHAwPX7o4DkVHbV659NiBPYnx8Rpbjbunl2+TZt36DWru156JfYHyjMOCKlWA3AYAgFK6cPpkzbr1yvYMJjM9LfT9cTs3rLWsTEtJuRh7avPKpb9s2+fuyY0WQPnFYUGVyG0AACqXk5195cK5Ts/2LcM2szMzPx710vGD+5ycXfq/PMY/oHe1x2qmp6XevHbl+MH9f/25mjMYoDzjsKBW5DZAZRcSEqJ0CMCjdTH2lDEvr37TFmXY5txvJx0/uK+mj+/ncxZX9aohV9rpdC7uHr5Nmj8/ZGQZ9gWgzHFYUCtyG6Cy8/PzUzoEoCwl3Lj+64xpuzevT0tObvrkU29++vWFUyeEEL5NmpmXSU9NWbVw7s71ay6fOytJ0uNPPPnyux/VbdTYvED81cu/Tp+2d+vG9NTUxq3bvvHfL3duWDPv2y+mhP3esEWri7Gn/ljyi87BMHH6HPMZDIByi8NC5UFuAwBQj0tnTn8wbFDSrZvyy/07tv539NAnnu4k2dj4NG4qV964EvfBsKDrcRfNnzr417b3YvZ/t2ztY7XrCiHOnzz+wfCglKRE87v/eeWl5n7+tlqtz+NNhBAr5s8ymUz9R75as249q64egOLjsFCpVIA5oAEAKIqszIxPXxuedOtmt36DZq2PWn747LSlayRJWhe2uJaPr07vIITIzsr6z6iXblyJ6zv8lem/b1p26MzCqIMvjp2QkZa6dM5MIURmRvrnb7yckpTYO3jI9N83LYuJnbZ0jdbObsuqZT6PN9Ha2Qkh9m7dKIToOYjnxwPlHYeFyqYC5DZBQUHR0dFKRwEAKO9WLZh77dLFfiNGj/96qpd3Ha2dnW+T5sPGv5+VmeHbtLm8zMpfZsedO/P2F/8b/cEntes3tLO3d/Wo+uLYCdVrecce+VsI8fvCudcvXwp+7V9vfvp17foN7XQ63ybNXxw7ITszs2HzVkKIhPgbiTfjq3rV8KjupeTaAigCDguVTQUYkxYREREYGNiuXTulAwEAlGubV0ZWcXUbOu49y0q9wVEI4dsk/yRm04oIIcT3E9/9fuK7+c/pMpnkQr3GTYUQm1cureLqNvjN8ZaNGJychBANWzwhhEhOTBBCVHF1feTrA6DUOCxUNhXgug0AAA+VlZlx6czpxq3b2uv0lvUHdmwV/9wxnJWZEXc2VghhzMsz5uWZjEaT0Wh+ErG7p5fcyOOt2thqtZaNHD+4X/xzEiO3fz3ukhVWCkBpcFiohCrAdRsAAB4qIy1NCGG+01d2MfbUygWzbTQa+cfXtORkIUSnZ/u9O+XH+zYi322cmZ5mWRl/9fLvC+c6ubh6edcWQlSvWcvJ2SXldtJf69e07/HMo1kbAGWAw0IlxHUboLILDQ0NDQ1VOgqgtFzcPfQGx6P7dq+YPystOTktJWXj8vCPRgTn5uTUrFtP/lXV2d3d4OS0e8uGPyN+TYi/kZubm3Dj+rH9e37+8r+rF8+TG3FwdDq8e+eaXxekpaRkpKX+9ecf/x4SmHI7qWGLVnJHko1N7xeGCiGmfTAhctaMKxfOZWdlJd2KP3v86Ialv30yZtjfe7hHFCgXOCxUQly3ASo75uqAajz74rDIWTNmf/3p7K8/FULYaDTBr/3r1+lTzY/n02hsg17717xvv/jh43cLfPaD7/5PLjz30ojw//thxqcfzvj0QyGEZGMzcNRrkbNmNGrxhHnhF8dOOHPs7/07ts6f8uX8KV9atiNJ0rvf3v/XXwDWx2GhsiG3AQCoxJB/vavR2G79fXnSrZv1mjR76a2QtJRkIYR5NiQhxMBRr3vXa7Dil1mXzpxOvZ3k7lndp1GTbgOC2nToIi/w4lshGlvbzSuXJt2Mr9ek2UtjJ8QePSyEaPrknafc2mq1n/zfgo3LwzevXHruxLHM9DQXj6rVHqv5xNOdOjzTx1ClinXXG8ADcViobCTzzVLlliRJYWFhQUFBSgcCqNOgQYOEEBEREUoHoqSk8asy/zwphEj09z777tNKh4NyJOHG9XGBz9jY2MzbvFuyYSB3pdC6/xK54BLaR9eroRV6zFx3MmnCKrm8fzkPSCnvOCyUEz7fRrnuvCiE0PVs6DK1j1xZAf49wsLC/P39lY4CAKB+cWdjp30YcvrI4cz0tIQb17f9seL9IQMSblx/cewEzmCAyonDQsVSAcakccUGAGAdcWdjNy4L27gszLKyZ9CLPQIHKxUSAGVxWKhYKkBuAwCPnEaS/18ylvdhunikWvp3CBrz1q5Nf16Lu6jVan0eb/rMC0M7PNNH6bhgPZLReOfFP0eGR86iIynPZLJavygCDgvl1p1vq8VXhtwGAISNo71c0KRlKxsJlKVzMAwb//6w8e8rHQgUo0nNMZdtquis06mNk/2dANKzcy1eQnEcFsotTWr+n2wbpztfVXIboLILCQlROgTlaR7Ln8FGF3db2UgAKEt3+c5BQFPdyTqdarzuTKKli7ud+ng16/QLVGi6y8lyQeN156takW6BCgoKku4nPDyc5Vme5Uu8vJ+fn5+f330bqTxsG+afSWgTM+2vpCgbDAAFOR6NlwuSg52mlot1OtXUcpEc7AoEAKAQ9ldStImZctm20Z2fAyrAHNBm0dHRly5durfe39+/Zs2aLM/yLF+aEMEiggAAFdpJREFU5Ss5U1r2Df8fTTl5QogrQ1pcHdhE6YgAKKPxhLX6c4lCCPsuvq7T+1ut38Q3l2dtiRVCZNR1PRba22r9AhVU9cijNRYfEkJIdppqf42VDPm/DlSk3AYAHp3E15ZmbT8rhMj2MByZ8bxJW5EuawMoE47HbjT8aKNcdv6yt75fU6t1nbH8yO2P1srlk190T23MsDTggaQcY9M3fre7mSaEsO/k4zpzoPkt/ngDgBBCOAS3kAt2N9M8V51QNhgA1icZTTXnHZDLNlV01nlqp5mud0Pz1AU15x1gzkagEJ6rTsiJjRDCIaiF5VvkNgAghBD2neppm3nJ5eqRR+0SMpSNB4CVuW85a4hNkMuG0U9JOq01e5d0WsPop/J7j01w33LWmr0DFYhdQkb1yKNyWdvMy75TPct3yW0AQAghhI1U5T8BwkYSQmgyc+r+7y8px/jQDwFQB13cbfNFG423q8PQ1taPwWFYa9u6bnK55pwD+gtJ1o8BKOekPFOdaTs1mTlCCCGJKh91k/9wm5HbAEA+bRNPfd/8WQQcj9+oPXOPsvEAsA7b25n1P9+mSct/sk2VD7tKdhrrhyFpNU7vd5HLmowc3y+3297OtH4YQHlWe/pup7+vy2V9v6ba5l4FFiC3AYA7qnzQzbZBVbnsvuWs96x9Uh6j3gE1095Mr//JFrsbqfJLw8gn7Tv6KBWMfUcfw8gn5bLdjdT6n2zR3kxXKhigXJHyTN6z9pmHa9o2qFrlg273WYx50gDAUt6V5FvBi4y38m9STG7pdfadp/MMVh15D8A69OcSfb/cZvdP/mDf0cd1+gChkQr/1KNlNCX+a0XW5lj5VY6r7syHndN83ZQMCVCaJjOn7pSdzvsuyy9tXPXuvw257xOoyG0AoKCcw1cTX400JuePBsmuaogb2SqxnbeyUQEoQ5rMHM/IY9VXHTffWadtVcNtVqD5GZoKMqVnJ74amX0g/zTOpLW51ufx64GN86w7vQFQTrhGX6w576BdfP5vjjZVdK4/B947Gk1GbgMA95F7LiHx9WV5FxPNNSlNq10b0CSlRXWTjaK/6QIoHU16jtvWc17Ljmpv3ZkOUffc486f95LsbRUMzJIpK/f2x+syVx831+S4668OaJLQuW6eAxkOKgXJaHI6dK36sqNOR26YKzXerq4zB5hn3bjPp8htAOC+jEkZSSG/Z0dfsKzMcdantPRMr+ua46wzKXG3MYCS0aTn2N9Ic4i95XT0hpSdZ/GGjeMb/o6vtRPl7VcLk0j9KTp1xk6Rd2fORpOdJqVJtXRf96xqBpIcqJJNVp5tcqbDuUSnmOva23c9j8GuXW2XKc/buOgL+Ti5DQAUJmvLmeQvNuZdSVY6EABlz+4p7yofdDXPIFIO5Z5LSPl6c9aOc0oHAijJppqj0/iO+j5NHvobBLkNADyEKSMn7Zd9GWExeddTlY4FQNnQtqphePlJXbf6SgdSJJmbTqfN3Ztz8LLSgQDWpvF01L/QyjCstaQv0oVKchsAKJo8Y/a+uKztZ3OOXss9m2BKyTJl5SodE4CikhztbFwdbOt72D1Rw76LbyHj9cut3LMJWVtjsw9czj1905iYbkrNVjoioOxJ9raSk72tj5u2SXX7jj52bWoKTTEeWkNuAwAAAEANeHYnAAAAADUgtwEAAACgBuQ2AAAAANSA3AYAAACAGpDbAAAAAFADchsAAAAAakBuAwAAAEANyG0AAAAAqIGt5YtLly7t2rVLqVAAVELu7u5du3ZVOgoAAKAGd+U20dHRwcHBSoUCoHKaMmXKhAkTlI4CAABUeLb3VplMJuvHAaASCg8PDw4ODgkJycrK+uCDD5QOBwAAVGz3yW0AwJqmTp06fvx4IQTpDQAAKA1yGwAKGzdunBCC9AYAAJQSuQ0A5ZHeAACA0ivJHNA//fSTJEmSJHl4eJR5QKUJo5wEpqwibgS2FcpKZGSk9I/StDNu3LipU6d++OGHX331VVnFBgAAKhWVX7e5du2al5eXXI6Ojvbz81M2HgCF4OoNAAAoDZXnNgDKv/DwcHP5scceGz58+Icffnj79u2vv/5awagAAECFU4Fzm9dee+21115TOgoAJefv7+/n53ffx2p988035DYAAKBYSnK/jSWj0Th58mQfHx+DwdCsWbMZM2aYH4+zbt06yYK9vX2tWrUCAwO3bt1q2cKPP/5ovvEjMzNz3Lhx1apVc3Z2HjhwYFxcnBBi1apVTz75pIODQ7169caNG5eSkiJ/8KF3jHTu3Nk8IE0I0a5dO3n5IUOGyDV5eXmzZ8/u2rWrh4eHVqt1c3Pr2LHjjBkzcnJyzJ+y7KWQlS1k+yxYsCAgIKBq1apardbDw6N3796rV6+2XKaIXRRxe1rKzc395JNPateurdPpmjZtOnPmzNJHWwjLFSm864du+QMHDphXMz09Xa7s1q2bXGkOafLkyXJN586di74KlnHKj1WpVauWRqNZsWJFIWs3ceJE+VNNmzY1V86ePVuudHFxkWtyc3OnTJny1FNPubi4aLXa2rVrBwQE/O9//7t69WqxtnPJgizxt6ko/yiy69evjxo1ytPT08HBoX379lu2bLlvJEXcl2rWrBkdHW26R1hYWCGrCQAAcH/3nk/ce55RgPk81d3d3ZwnmP3www/yYmvXrr1vj5IkzZkzx9zaDz/8INe7ubn9f3v3HhRl9QZw/CxLy10LBUEhFdQ0TcPUsNHEcKSacRrzluNMoGHTbYJEm2mcvMxkWuZkDV0sg0lmuliJiY5GXsbLgBheyEERzEuSKJohrMBye39/nH5n3pZlWRZW8u37+evl2bPnPOfsLvM++1522rRp+pbR0dEfffSR3dNnzJjROg2HkUmTJjlMYN68eZqmWa3WRx991GGDcePG3bx5s0OTdai2tnbKlCkOh3jttdc8tJ763mbNmmXXeNGiRW2tnovZuvjGcDK0Kyvf0tISEhIig7m5uZqm1dfX+/n52XWVkJAgI6tWrXJjwYODg5966inVJjs728nsli5dKpuNGDFCBT///HMZ7Nmzp4wsXLjQYQIJCQnuvSs6lKTbnyYXPw7Xrl0bOHCg/lGz2ZycnKz+7NAcnXDxfxEAAIBep2obIcTYsWNLSkoqKirUF+eDBg1q/ZSmpqby8vLXX39d7XjZbDb5kNobE0I88cQTFRUVRUVFvr6+KrhmzZqbN2++++67KlJeXq65UNtomqb/stzu6+GXX35ZxgMDA7du3VpdXf3TTz8FBwfLYFJSktuTVV599VXZLDw8fN++fbdu3dq9e3fPnj1l8LvvvvPEeup7mzBhQllZ2bVr19RkhRAFBQUO18rFbF18YzgZ2sWVnzt3roy88cYbmqbpD0/FxMRomtbQ0BAQECAjv/zyi3sLPnTo0IMHD9bX17c7O1XbjBw5UgVb1zb+/v5CCLPZfODAAZvNdvny5f3796empiYmJrr9rnA9Sbc/TS6+KKpyCwoK2r59e3V1dXZ2tpyy1KE5OkFtAwAA3NDZ2ubYsWMyuGnTJhkxm82NjY0On6hOLhJCHD58WAb1e2OlpaUyOGbMGBm57777ZKSyslI127dvn9a52sZmswUGBsr4kiVLVHzVqlUyaLFYampqOjNZ/RAbN25U8bS0NBl87LHHPLGe+t5OnjypkgkNDZXB1NTU1mvlerZOuDK06yufmZkpI7GxsZqmLV++XAgxevRoIYSXl9eNGzcOHjyoptDc3Ozegqt1a5eqbUaNGqWCrWsbeYakl5dXRkZGaWlpQ0ODvhNPJ+nep8nFF6WpqalHjx4ysnjxYtXslVdeUb11aI5OUNsAAAA3dOp6Gx8fnwcffFDt28mN5ubm+vp6IURDQ8P7778/adKk0NBQi8ViMpn03+9euXLFrjdfX9/BgwfLbbULNWrUKLmh9paEEFartTNpCyEuXryoOlF7fvrthoaGs2fP6p/ifLLOh0hOTlbXyaxbt04Gf/31V7undO16+vj4DB8+XG5bLBa1febMmS7J1gknQ7u+8lOnTpWRwsJCq9Uqr+tISkoaOHBgS0vL/v379+7dKxtMmTLFy8vLjSlYLJaxY8e6Pi9XzJ8/XwjR0tKyYMGCIUOG+Pv7jxgxIiUl5cKFC8KtdXYvyQ59mlx8Ua5cuVJdXS0jssiUYmJi9EN37XsJAADAdZ26T1pgYKD6tT4vL/sy6emnn96xY0dbz7W7QFkIoc4vEkKoboOCguRGc3NzZ1K1o+nuAaD/wUGt7XsDOJ+sG1pXaF27nl2r8/Wk5PrK9+3bd/jw4cXFxU1NTbm5uQUFBUKIyZMnnzhx4vz58/v27SsqKpItVRXkXOspBAUFufFStrS0qG21r6+sWbNm6NChmzdvPn78eGVlZVNTU3FxcXFx8Q8//ODKPn1XJdmhT5MbH4fO6Kr3EgAAgJ0u2Ed36NKlS2pHfNmyZTdu3NA07fr16x4ari1t7agNGDBA7fwVFhaq+LFjx+SGxWIZNGiQ6wNVVVWp76d37dolhOjfv7/6djwrK6v1IbO6ujrX+3djPW0226lTp+R2Q0NDcXGx3B4yZEjrxl2brZOhO7Tyqmh5++23bTZbSEjI8OHDJ0+eLITYuXPn4cOH9c26dgqtqbSrqqpU8MiRI3bNvLy8FixYsGvXrqtXr9bU1Bw4cECekvfHH3/s37/f00m6x8UXJSwsTB0CUg8JIY4fP67v7d85RwAA8F/gqdrmrrvuUttBQUF+fn4XLlx4/vnnPTRcW3r06KG+8z506FBTU5PctlgsSUlJcvuTTz7JycmxWq27d+9Wp83MnTtXf96OGywWizw9SQixePHibdu23bx5s6am5tSpU19//fWMGTM+/PBD13tzbz1feumlc+fOXb9+fdGiReoSC3WNvueydTJ0h1Ze1TZHjx4VQsTFxZlMJlnblJWV2Ww2IcSwYcMiIiI8MQU76hSvS5cuffPNN9XV1ZmZmd9//71ds8cff3zlypUFBQVXr1718fHRv4saGxs9naR7XHxRzGbz7NmzZWTDhg07duywWq0//vhjRkaGXW//wjkCAID/BP33qW7cA1oFc3JyVJ/yWnB1f15Ff3tcda8kdfWzvrf4+HgZfO6552RE/0McOTk5DtNwmNjEiRPt0pDfJTu/6W1VVVWHJvvXX3+pyM6dO2WzW7duqYm0tnr1ak+sp/7ewTNnzrR7SkpKSluDupitK28M50O7uPKaptXW1vr4+KhH5a/9aJqmygx9t51c8HbV1dXZ3f7Y399fvQTqXgLR0dEOR+/fv7+8k7JHk3T70+Tii1JZWTlgwAD9ow7vAd359xL3EgAAAG7w1HEbIcS3336blpY2YMAAHx+f6Ojod955Jz093XPDtSUrK2v69Om9evXSn58mhAgICNi7d+9nn30WFxd3zz33mM3mu+++e8KECenp6YcOHVKX8neGv79/bm5uVlZWQkJCaGiot7d3r169Ro4cmZiYuHXr1pSUlA711tH1NJlMX3311bJly+69916LxTJs2LD09PT169ffhmydD+36yvv5+elLU3nERr8h/nmxTdcuuB1fX989e/bMnDkzPDw8ICBg6tSp+fn548aNs2u2Z8+etWvXxsXFRUZGent7BwQEjBgxIi0traCgQJ7Q5dEk3ebiixISEpKXlzd//vzevXv7+vqOHz/+559/bl11/zvnCAAADM+k6a5C2bx585w5czTPXEAMw/v0009ffPFFIUSvXr1u/7VVMBL+FwEAADd48LgNAAAAANw21DboAFPbVqxY0d3ZddYdMbs7IkkAAIBuQW0DAAAAwAg69dud+K9p9/qHF1544fZk4gl3xNUdd0SSAAAA3YLjNgAAAACMgNoGAAAAgBFQ2wAAAAAwAmobAAAAAEZAbQMAAADACKhtAAAAABgBtQ0AAAAAI6C2AQAAAGAE1DYAAAAAjIDaBgAAAIARUNsAAAAAMAJqGwAAAABGQG0DAAAAwAiobQAAAAAYAbUNAAAAACOgtgEAAABgBNQ2AAAAAIyA2gYAAACAEVDbAAAAADACahu0KSgoyOTUhAkTujtHAAAA4G/UNnCsvLzcarU6bzNkyJDbkwwAAADQLmobOBYREaHpfPHFF0KIlStX6oMZGRndnSYAAADwN2obuOTYsWNCiIceeqi7EwEAAAAco7aBS44ePSqEGD16tD64YcMGk8m0ZcuW7Ozs2NhYPz+/J598UgiRmJhoMpmuXr2qb/zss8+aTKZr166pSHV19VtvvRUTExMQEBAYGJiQkFBUVHRbZgMAAAAD8u7uBHAHaG5uLioqCg8PDw8P18cLCwuFENu2bfvyyy9l5P777xdC5OfnR0VF9enTR984Ly8vMjIyJCRE/nnx4sXJkyefP39eNcjNzc3Pzz969OjgwYM9Oh0AAAAYEsdt0L7Tp0/X1dW1PiFN1jZbtmxZt27d77//rmnae++99+eff5aVlT3yyCP6lpWVlb/99tuYMWPkn/X19QkJCRcvXkxNTT158mRdXV1FRcWKFStqamrWrl17eyYFAAAAg+G4DdonT0izq21sNltxcbHZbM7Ozo6Pj1fx/Px8IYRdbZOXl6fvYf369WfOnMnMzExKSpKRsLCw5cuXb9q0SY4FAAAAdBTHbdA+hxfbnDhxorGxcdq0afrCRvy/thk/frw+KGsbddxGnsOWnJzs7e1tNpvNZrOXl5fJZDp37pymaZ6cCgAAAAyL4zZon8ObpMkT0mbOnGnX+MiRI4GBgQ888IA+uG3bNtVDbW1tSUmJEKK5ubn1WBEREV2ZOgAAAP4zOG6DdrS0tJw4caJPnz79+vXTx2VtY3d8RghRWloaERFhNptVJCMj48yZM/379+/du7cQoqqqSggxd+5czRFZBQEAAAAdRW2DdpSUlNy6dcvuhDQhRGFhYUhISFRUlF3cYrGcPXt269at9fX158+ff/PNN9PS0oTuhLTQ0NCePXvm5ORs3LixoqKisbHx8uXLhw4dSk1NTU9Pvw0zAgAAgCFR26AdDk9Iq62tPX369MMPP9y6fXx8fFNT0/Tp0/38/KKioj7++ONFixbpe/D29l66dKnVal24cGHfvn0tFku/fv0mTpz4wQcfhIWFeX5CAAAAMCZqG7SjrRsJNDc3x8bGtm6/evXqefPmBQcHBwcHP/PMM4WFhb6+vkJ33EYIsWTJku3bt8fHx/ft29fX1zc6OnrGjBk5OTnTp0/38GwAAABgWCb9bak2b948Z84cblQFoHvxvwgAALiB4zYAAAAAjIDaBgAAAIARUNsAAAAAMAJqGwAAAABGQG0DAAAAwAiobQAAAAAYAbUNAAAAACOgtgEAAABgBN6tQ7Nnz779eQCAcunSpe5OAQAA3Hn+UdtERkbOmjWru1IBACkyMjIyMrK7swAAAHcYk6Zp3Z0DAAAAAHQW19sAAAAAMAJqGwAAAABGQG0DAAAAwAj+B/MlihDEA76bAAAAAElFTkSuQmCC' alt='Graphviz graph of the pipeline' style='width: 100%' />

## Validate, then run

`--dry-run` parses the config, opens the input headers, builds the DAG and
checks every contract, without executing a node. Only then is it worth
spending compute.

```python {.marimo}
conduit("run", str(rel(config_path)), "--dry-run")
conduit("run", str(rel(config_path)))
```

<!-- @output:Hstk -->

<pre style="white-space: pre-wrap; overflow-wrap: break-word;">Dry run for recipes/pipeline_101/config.toml
  ✓ config parsed
  ✓ inputs loaded: 1 variable(s) from 1 source(s)
  - input checks: none configured
  ✓ DAG built (static contract check passed)
  ✓ execution plan valid: 2 output node(s) reachable
  ✓ input contracts validated
      units     enabled=True  on_missing=warn  on_inexact=convert
      schema    on_mismatch=error
      temporal  on_uninferable=warn
  ✓ output paths writable: 1 destination(s)
Dry run passed.
</pre>

```python {.marimo}
result = xr.open_dataset(results_dir / "anomaly.nc")
```

<!-- @output:iLit -->

<span class="markdown prose dark:prose-invert contents"><h2 id="the-output">The output</h2>
<span class="paragraph">The written file carries the units declared on the nodes, and its attributes
include the config that produced it, along with a SHA-256 of that text.</span>
<ul>
<li><code>temperature_anomaly</code> — degC</li>
<li><code>anomaly_range</code> — degC</li>
</ul></span>

```python {.marimo}
result
```

<!-- @output:ZHCJ -->

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
    temperature_anomaly  (time, site) float64 2kB ...
    anomaly_range        (site) float64 24B ...
Attributes:
    units:                  degC
    long_name:              near-surface air temperature
    conduit_config:         # The smallest pipeline that still has every movi...
    conduit_config_sha256:  398cf5d57f2fcd06bda47eb89779f0a34b13318238b742adb...</pre><div class='xr-wrap' style='display:none'><div class='xr-header'><div class='xr-obj-type'>xarray.Dataset</div></div><ul class='xr-sections'><li class='xr-section-item'><input id='section-713af159-b303-4e85-8b36-2116899d96e1' class='xr-section-summary-in' type='checkbox' disabled /><label for='section-713af159-b303-4e85-8b36-2116899d96e1' class='xr-section-summary'>Dimensions:</label><div class='xr-section-inline-details'><ul class='xr-dim-list'><li><span class='xr-has-index'>time</span>: 90</li><li><span class='xr-has-index'>site</span>: 3</li></ul></div></li><li class='xr-section-item'><input id='section-e21d4ba2-2fc9-47e9-b056-eac0a350edbf' class='xr-section-summary-in' type='checkbox' checked /><label for='section-e21d4ba2-2fc9-47e9-b056-eac0a350edbf' class='xr-section-summary' title='Expand/collapse section'>Coordinates: <span>(2)</span></label><div class='xr-section-inline-details'></div><div class='xr-section-details'><ul class='xr-var-list'><li class='xr-var-item'><div class='xr-var-name'><span class='xr-has-index'>time</span></div><div class='xr-var-dims'>(time)</div><div class='xr-var-dtype'>datetime64&#91;ns&#93;</div><div class='xr-var-preview xr-preview'>2020-01-01 ... 2020-03-30</div><input id='attrs-7e1dec50-80f0-4dfa-8708-ceea4d0362f6' class='xr-var-attrs-in' type='checkbox' disabled><label for='attrs-7e1dec50-80f0-4dfa-8708-ceea4d0362f6' title='Show/Hide attributes'><svg class='icon xr-icon-file-text2'><use xlink:href='#icon-file-text2'></use></svg></label><input id='data-b0383c50-801a-4b4d-a5e3-025a97422614' class='xr-var-data-in' type='checkbox'><label for='data-b0383c50-801a-4b4d-a5e3-025a97422614' title='Show/Hide data repr'><svg class='icon xr-icon-database'><use xlink:href='#icon-database'></use></svg></label><div class='xr-var-attrs'><dl class='xr-attrs'></dl></div><div class='xr-var-data'><pre>array(&#91;'2020-01-01T00:00:00.000000000', '2020-01-02T00:00:00.000000000',
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
      dtype='datetime64&#91;ns&#93;')</pre></div></li><li class='xr-var-item'><div class='xr-var-name'><span class='xr-has-index'>site</span></div><div class='xr-var-dims'>(site)</div><div class='xr-var-dtype'><U1</div><div class='xr-var-preview xr-preview'>'a' 'b' 'c'</div><input id='attrs-6151cd35-a8ea-46c2-9733-f60319705cde' class='xr-var-attrs-in' type='checkbox' disabled><label for='attrs-6151cd35-a8ea-46c2-9733-f60319705cde' title='Show/Hide attributes'><svg class='icon xr-icon-file-text2'><use xlink:href='#icon-file-text2'></use></svg></label><input id='data-fbc84639-78f6-414a-ae0d-c74451cd4619' class='xr-var-data-in' type='checkbox'><label for='data-fbc84639-78f6-414a-ae0d-c74451cd4619' title='Show/Hide data repr'><svg class='icon xr-icon-database'><use xlink:href='#icon-database'></use></svg></label><div class='xr-var-attrs'><dl class='xr-attrs'></dl></div><div class='xr-var-data'><pre>array(&#91;'a', 'b', 'c'&#93;, dtype='<U1')</pre></div></li></ul></div></li><li class='xr-section-item'><input id='section-e5d20a14-b1e6-4825-aa30-2afeaa1b4d5a' class='xr-section-summary-in' type='checkbox' checked /><label for='section-e5d20a14-b1e6-4825-aa30-2afeaa1b4d5a' class='xr-section-summary' title='Expand/collapse section'>Data variables: <span>(2)</span></label><div class='xr-section-inline-details'></div><div class='xr-section-details'><ul class='xr-var-list'><li class='xr-var-item'><div class='xr-var-name'><span>temperature_anomaly</span></div><div class='xr-var-dims'>(time, site)</div><div class='xr-var-dtype'>float64</div><div class='xr-var-preview xr-preview'>...</div><input id='attrs-6bd339f3-81c5-4bfa-aff2-57b11d05fae8' class='xr-var-attrs-in' type='checkbox' ><label for='attrs-6bd339f3-81c5-4bfa-aff2-57b11d05fae8' title='Show/Hide attributes'><svg class='icon xr-icon-file-text2'><use xlink:href='#icon-file-text2'></use></svg></label><input id='data-a9ae508c-cda8-4da9-9488-92d8b007f460' class='xr-var-data-in' type='checkbox'><label for='data-a9ae508c-cda8-4da9-9488-92d8b007f460' title='Show/Hide data repr'><svg class='icon xr-icon-database'><use xlink:href='#icon-database'></use></svg></label><div class='xr-var-attrs'><dl class='xr-attrs'><dt><span>units :</span></dt><dd>degC</dd><dt><span>long_name :</span></dt><dd>near-surface air temperature</dd></dl></div><div class='xr-var-data'><pre>&#91;270 values with dtype=float64&#93;</pre></div></li><li class='xr-var-item'><div class='xr-var-name'><span>anomaly_range</span></div><div class='xr-var-dims'>(site)</div><div class='xr-var-dtype'>float64</div><div class='xr-var-preview xr-preview'>...</div><input id='attrs-38a2f02a-5fdb-4ff3-b782-55c6e12e09c2' class='xr-var-attrs-in' type='checkbox' ><label for='attrs-38a2f02a-5fdb-4ff3-b782-55c6e12e09c2' title='Show/Hide attributes'><svg class='icon xr-icon-file-text2'><use xlink:href='#icon-file-text2'></use></svg></label><input id='data-12828f98-0cbd-4ee4-b128-9c9b4ad0829c' class='xr-var-data-in' type='checkbox'><label for='data-12828f98-0cbd-4ee4-b128-9c9b4ad0829c' title='Show/Hide data repr'><svg class='icon xr-icon-database'><use xlink:href='#icon-database'></use></svg></label><div class='xr-var-attrs'><dl class='xr-attrs'><dt><span>units :</span></dt><dd>degC</dd><dt><span>long_name :</span></dt><dd>near-surface air temperature</dd></dl></div><div class='xr-var-data'><pre>&#91;3 values with dtype=float64&#93;</pre></div></li></ul></div></li><li class='xr-section-item'><input id='section-5d1d7904-c5bb-400e-b5f3-e967fd393ac9' class='xr-section-summary-in' type='checkbox' checked /><label for='section-5d1d7904-c5bb-400e-b5f3-e967fd393ac9' class='xr-section-summary' title='Expand/collapse section'>Attributes: <span>(4)</span></label><div class='xr-section-inline-details'></div><div class='xr-section-details'><dl class='xr-attrs'><dt><span>units :</span></dt><dd>degC</dd><dt><span>long_name :</span></dt><dd>near-surface air temperature</dd><dt><span>conduit_config :</span></dt><dd># The smallest pipeline that still has every moving part: an input file, an
# imported node function, an inline node, and an output file.

&#91;inputs.climate&#93;
path = "data/climate.nc"
vars = &#91;"temperature"&#93;

# Any section conduit does not recognise is one of your own modules, and must
# say where to import it from.
&#91;climate_nodes&#93;
_import_path = "recipes.pipeline_101.nodes"

# Glue that does not deserve a Python module can be declared inline.
&#91;&#91;node&#93;&#93;
name = "anomaly_range_climate"
inputs = &#91;"temperature_anomaly_climate"&#93;
expression = "temperature_anomaly_climate.max('time') - temperature_anomaly_climate.min('time')"
units = "degC"

&#91;outputs.climate&#93;
path = "results/anomaly.nc"
vars = { temperature_anomaly_climate = "temperature_anomaly", anomaly_range_climate = "anomaly_range" }
</dd><dt><span>conduit_config_sha256 :</span></dt><dd>398cf5d57f2fcd06bda47eb89779f0a34b13318238b742adb51797c5a9462952</dd></dl></div></li></ul></div></div>