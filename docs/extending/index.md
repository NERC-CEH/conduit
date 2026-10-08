---
title: Extending conduit
icon: lucide/blocks
---

# Extending conduit

These pages are for building a package *on* conduit: a library of node modules your group shares, a tool that drives pipelines, or a domain package that wraps conduit.
To write node functions and configs, see the [Guides](../guides/install.md).

## What you can extend

At present, one thing: **modules**.
An installed package can [register its node modules](register-modules.md) so configs name them by section header alone, with no `_import_path`.

Input checks (`conduit.input_checks.CHECKS`) and file formats (`conduit.formats`) are not extension points yet; a new check or format has to go into conduit itself.

## Build on the library, not the CLI

The CLI needs an extra your users may not have, and everything it does is a library call.
Build against `conduit.run`, `conduit.dry_run`, `conduit.load_config` and `conduit.build_graph`; see [Drive conduit from Python](../guides/run/drive-from-python.md) and the [Python API](../reference/python-api.md).

`run` accepts a `ParsedConfig` as well as a path, so a tool can load a config, change it in Python, and run it.
A run from a `ParsedConfig` writes no [provenance stamp](../reference/data-formats.md#output-provenance), so if your package builds configs in memory, decide what you want recorded.

## Stability

conduit is alpha, and breaking changes land without deprecation shims.
The config schema and the names in the [Python API](../reference/python-api.md) change rarely; pin a version if you need a guarantee.
