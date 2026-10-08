---
title: Installation
icon: lucide/download
---

# Installation

conduit needs Python 3.12 or later, and is installed from GitHub rather than PyPI.

## Install

=== "pip"

    ```sh
    pip install git+https://github.com/NERC-CEH/conduit
    ```

=== "uv"

    ```sh
    uv add git+https://github.com/NERC-CEH/conduit
    ```

This installs the library and its Python API.
The `conduit` command, geospatial support and graph rendering are optional extras.

## Extras

| Extra | Installs | Needed for |
| --- | --- | --- |
| `cli` | `typer` | the `conduit` command (`conduit run`, `conduit graph`, `conduit gridded`) |
| `geo` | `rioxarray`, `pyproj` | CRS-aware gridded inputs (`(y, x)` → `pixel` stacking, computed `latitude`/`longitude`) |
| `viz` | `apache-hamilton[visualization]` | rendering the DAG with `conduit graph` |
| `all` | everything above | every optional feature |

Non-gridded pipelines never need `geo`: it is imported only when an input carries CRS metadata.

Name extras in square brackets:

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

## Graphviz

`conduit graph` also needs the Graphviz system binaries, which the `viz` extra cannot install:

```sh
# Ubuntu/Debian
sudo apt install graphviz

# macOS
brew install graphviz
```

## Verify installation

```sh
python -c "import conduit; print(conduit.__version__)"
conduit --version  # with the cli extra
```

Then try [Pipeline 101](../recipes/pipeline-101.md).
To set up a development checkout, see [`CONTRIBUTING.md`](https://github.com/NERC-CEH/conduit/blob/main/CONTRIBUTING.md).
