---
title: Installation
icon: lucide/download
---

# Installation

conduit is currently only available from GitHub.

## Prerequisites

- **Python 3.13** or later

## Install into an existing project

=== "pip"

    ```sh
    pip install git+https://github.com/NERC-CEH/conduit
    ```

=== "uv"

    ```sh
    uv add git+https://github.com/NERC-CEH/conduit
    ```

This installs the `conduit` library: the core engine (Hamilton, xarray, contract
checking, the config parser) and its Python API, `conduit.run`, `conduit.dry_run` and
`conduit.build_graph`.

The `conduit` command is an optional wrapper over that API and lives in the `cli`
extra, along with geospatial and DAG-visualisation support (see below).
Install it with `conduit[cli]` if you want to drive pipelines from a terminal.

## Optional features (extras)

conduit groups its optional dependencies into installable extras:

| Extra | Installs | Needed for |
| --- | --- | --- |
| `cli` | `typer` | the `conduit` command (`conduit run`, `conduit graph`, `conduit gridded`) |
| `geo` | `rioxarray`, `pyproj` | CRS-aware gridded inputs (`(y, x)` → `pixel` stacking, computed `latitude`/`longitude`) |
| `viz` | `apache-hamilton[visualization]` | rendering the DAG with `conduit graph` |
| `all` | everything above | convenience — installs every optional feature |

The `geo` dependencies are imported lazily and only when an input carries CRS metadata,
so non-gridded pipelines never need them.

Append the extra(s) in square brackets:

=== "pip"

    ```sh
    pip install "conduit[geo] @ git+https://github.com/NERC-CEH/conduit"
    pip install "conduit[all] @ git+https://github.com/NERC-CEH/conduit"
    ```

=== "uv"

    ```sh
    uv add "conduit[geo] @ git+https://github.com/NERC-CEH/conduit"
    uv add "conduit[all] @ git+https://github.com/NERC-CEH/conduit"
    ```

## System dependencies

### Graphviz (for pipeline visualisation)

The `viz` extra installs the Python `graphviz` bindings, but `conduit graph` also
needs the Graphviz system binaries:

```sh
# Ubuntu/Debian
sudo apt install graphviz

# macOS
brew install graphviz
```

## Verify installation

```python
python -c "import conduit; print(conduit.__version__)"
```

With the `cli` extra:

```sh
conduit --version
```

## Next steps

- Build your first pipeline in the [Quickstart tutorial](first-pipeline.md).
- Contributors setting up a development checkout should follow the
  [`CONTRIBUTING.md`](https://github.com/NERC-CEH/conduit/blob/main/CONTRIBUTING.md)
  guide instead (`git clone` + `uv sync`).
