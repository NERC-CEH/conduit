---
title: Extending conduit
icon: lucide/blocks
---

# Extending conduit

These pages are for building a package *on* conduit rather than a pipeline *with* it: a library of node modules your group shares, a tool that drives pipelines, a domain package that wraps conduit in something more specific.
If you are writing node functions and configs, [Guides](../guides/install.md) is the place to be instead.

## What you can extend

One thing, at present: **modules**.
An installed package can register its node modules so configs name them by section header alone, with no `_import_path`.
[Register modules from a package](register-modules.md) is the whole of it.

Two other registries are not extension points yet.
Input checks (`conduit.input_checks.CHECKS`) are validated when the config is parsed, before any downstream package has been imported, and the file formats in `conduit.formats` are a fixed tuple.
Both are on the roadmap; until then, a check or a format has to go into conduit itself.

## Building on the library, not the CLI

Everything `conduit run` does is a call into the library, and the CLI installs with an extra that your users may not have.
Build against `conduit.run`, `conduit.dry_run`, `conduit.load_config` and `conduit.build_graph`, never against the command line.
[Drive conduit from Python](../guides/run/drive-from-python.md) walks through the individual steps, and [Python API](../reference/python-api.md) indexes every name.

Two things are worth knowing before you wrap any of it:

- **`run` accepts a `ParsedConfig`, not just a path.** Load a config, adjust it in Python, then run it. That is the seam for a tool that generates or rewrites configs.
- **Provenance follows the config text.** A run from a *path* stamps the config and its SHA-256 onto every output. A run from a `ParsedConfig` has no text to stamp, so it stamps nothing. If your package builds configs in memory, decide what you want written and say so in your own docs.

## What is stable

conduit is alpha, and breaking changes land without deprecation shims.
In practice the config schema and the names in the [Python API](../reference/python-api.md) reference change rarely, and these docs move with them.
Pin a version if you need the guarantee.

## Where next

- [Register modules from a package](register-modules.md) — the entry-point group, and what conduit does with it.
- [Drive conduit from Python](../guides/run/drive-from-python.md) — every step `run` takes, individually.
- [Configuration reference](../reference/configuration.md) — the schema your users write against.
