---
title: Extending catena
icon: lucide/blocks
---

# Extending catena

These pages are for building a package *on* catena: a library of node modules your group shares, a tool that drives pipelines, or a domain package that wraps catena.
To write node functions and configs, see the [Guides](../guides/install.md).

## What you can extend

At present, one thing: **modules**.
An installed package can [register its node modules](register-modules.md) so configs name them by section header alone, with no `_import_path`.

Input checks (`catena.input_checks.CHECKS`) and file formats (`catena.formats`) are not extension points yet; a new check or format has to go into catena itself.

## Build on the library, not the CLI

The CLI needs an extra your users may not have, and everything it does is a library call.
Build against `catena.run`, `catena.dry_run`, `catena.load_config` and `catena.build_graph`; see [Drive catena from Python](../guides/run/drive-from-python.md) and the [Python API](../reference/python-api.md).

`run` accepts a `ParsedConfig` as well as a path, so a tool can load a config, change it in Python, and run it.
A run from a `ParsedConfig` writes no [provenance stamp](../reference/data-formats.md#output-provenance), so if your package builds configs in memory, decide what you want recorded.

## Stability

catena is alpha, and breaking changes land without deprecation shims.
The config schema and the names in the [Python API](../reference/python-api.md) change rarely; pin a version if you need a guarantee.
