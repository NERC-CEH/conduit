---
title: Installation
icon: lucide/download
---

# Installation

conduit is installed from GitHub; it is not on PyPI.

!!! warning "Alpha"

    conduit has no users outside the core team yet.
    The config schema, the Python API and the CLI all change without deprecation warnings, so pin a commit if you need a build to keep working.

## Prerequisites

- **Python 3.12** or later. CI tests 3.12, 3.13 and 3.14.

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

The `conduit` command is an optional wrapper over that API. It lives in the `cli` extra,
alongside geospatial and DAG-visualisation support (see below). Install `conduit[cli]` if
you want to drive pipelines from a terminal.

## Optional features (extras)

conduit groups its optional dependencies into installable extras:

| Extra | Installs | Needed for |
| --- | --- | --- |
| `cli` | `typer` | the `conduit` command (`conduit run`, `conduit graph`, `conduit gridded`) |
| `geo` | `rioxarray`, `pyproj` | CRS-aware gridded inputs (`(y, x)` → `pixel` stacking, computed `latitude`/`longitude`) |
| `viz` | `apache-hamilton[visualization]` | rendering the DAG with `conduit graph` |
| `all` | everything above | convenience — installs every optional feature |

conduit imports the `geo` dependencies lazily, and only when an input carries CRS
metadata, so non-gridded pipelines never need them.

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

- Build your first pipeline with [Pipeline 101](../recipes/pipeline-101.md).
- Contributors setting up a development checkout should follow the
  [`CONTRIBUTING.md`](https://github.com/NERC-CEH/conduit/blob/main/CONTRIBUTING.md)
  guide instead (`git clone` + `uv sync`).
