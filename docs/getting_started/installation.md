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

This installs the `conduit` package and the `conduit` CLI command into your environment.

The base install is intentionally lightweight — it includes the core engine
(Hamilton, xarray, units checking, the config parser and the CLI). Geospatial and
DAG-visualisation support are optional extras (see below).

## Optional features (extras)

conduit groups its optional dependencies into installable extras:

| Extra | Installs | Needed for |
| --- | --- | --- |
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

## Install for development

```sh
git clone https://github.com/NERC-CEH/conduit.git
cd conduit
uv sync
source .venv/bin/activate
```

`uv sync` installs every optional extra (`geo` and `viz`) along with the development
tooling, so you don't need to request them explicitly.

## System dependencies

### Graphviz (for pipeline visualization)

The `viz` extra installs the Python `graphviz` bindings, but `conduit graph` also
needs the Graphviz system binaries:

```sh
# Ubuntu/Debian
sudo apt install graphviz

# macOS
brew install graphviz
```

## Verify installation

```sh
conduit version
```
