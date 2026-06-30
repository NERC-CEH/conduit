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
    pip install git+https://github.com/breadboard/breadboard
    ```

=== "uv"

    ```sh
    uv add git+https://github.com/breadboard/breadboard
    ```

This installs the `breadboard` package and the `breadboard` CLI command into your environment.

The base install is intentionally lightweight — it includes the core engine
(Hamilton, xarray, units checking, the config parser and the CLI) but **not** the
built-in ecological models or the DAG visualization support. Install those via the
extras below.

## Optional features (extras)

breadboard groups its optional dependencies into installable extras:

| Extra | Installs | Needed for |
| --- | --- | --- |
| `models` | `pyrealm`, `rothc-py`, `sgam` | the built-in P-model, SPLASH, SGAM and RothC models |
| `viz` | `apache-hamilton[visualization]` | rendering the DAG with `breadboard graph` |
| `all` | everything above | convenience — installs every optional feature |

Append the extra(s) in square brackets:

=== "pip"

    ```sh
    pip install "breadboard[models] @ git+https://github.com/breadboard/breadboard"
    pip install "breadboard[all] @ git+https://github.com/breadboard/breadboard"
    ```

=== "uv"

    ```sh
    uv add "breadboard[models] @ git+https://github.com/breadboard/breadboard"
    uv add "breadboard[all] @ git+https://github.com/breadboard/breadboard"
    ```

## Install for development

```sh
git clone https://github.com/breadboard/breadboard.git
cd breadboard
uv sync
source .venv/bin/activate
```

`uv sync` installs every optional extra (`models` and `viz`) along with the
development tooling, so you don't need to request them explicitly.

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
