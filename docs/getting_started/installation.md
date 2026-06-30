---
title: Installation
icon: lucide/download
---

# Installation

breadboard is currently only available from GitHub.

## Prerequisites

- **Python 3.13** or later

## Install into an existing project

=== "pip"

    ```sh
    pip install git+https://github.com/NERC-CEH/breadboard
    ```

=== "uv"

    ```sh
    uv add git+https://github.com/NERC-CEH/breadboard
    ```

This installs the `breadboard` package and the `breadboard` CLI command into your environment.

The base install is intentionally lightweight — it includes the core engine
(Hamilton, xarray, units checking, the config parser and the CLI). Geospatial and
DAG-visualisation support are optional extras (see below).

## Optional features (extras)

breadboard groups its optional dependencies into installable extras:

| Extra | Installs | Needed for |
| --- | --- | --- |
| `geo` | `rioxarray`, `pyproj` | CRS-aware gridded inputs (`(y, x)` → `pixel` stacking, computed `latitude`/`longitude`) |
| `viz` | `apache-hamilton[visualization]` | rendering the DAG with `breadboard graph` |
| `all` | everything above | convenience — installs every optional feature |

The `geo` dependencies are imported lazily and only when an input carries CRS metadata,
so non-gridded pipelines never need them.

Append the extra(s) in square brackets:

=== "pip"

    ```sh
    pip install "breadboard[geo] @ git+https://github.com/NERC-CEH/breadboard"
    pip install "breadboard[all] @ git+https://github.com/NERC-CEH/breadboard"
    ```

=== "uv"

    ```sh
    uv add "breadboard[geo] @ git+https://github.com/NERC-CEH/breadboard"
    uv add "breadboard[all] @ git+https://github.com/NERC-CEH/breadboard"
    ```

## Install for development

```sh
git clone https://github.com/NERC-CEH/breadboard.git
cd breadboard
uv sync
source .venv/bin/activate
```

`uv sync` installs every optional extra (`geo` and `viz`) along with the development
tooling, so you don't need to request them explicitly.

## System dependencies

### Graphviz (for pipeline visualization)

The `viz` extra installs the Python `graphviz` bindings, but `breadboard graph` also
needs the Graphviz system binaries:

```sh
# Ubuntu/Debian
sudo apt install graphviz

# macOS
brew install graphviz
```

## Verify installation

```sh
breadboard version
```
