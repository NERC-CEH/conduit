---
title: Register modules from a package
icon: lucide/package-plus
---

# Register modules from a package

If you maintain a package of node modules that several pipelines share, you can register those modules with conduit.
A config then names one by its section header alone, with no `_import_path`:

```toml
[diagnostics]
threshold = 0.3
```

rather than repeating the import path in every config that uses it:

```toml
[diagnostics]
_import_path = "science.diagnostics"
threshold = 0.3
```

## Declare the entry points

Registration is an ordinary [entry point](https://packaging.python.org/en/latest/specifications/entry-points/) in the `conduit.modules` group.
In your package's `pyproject.toml`:

```toml
[project.entry-points."conduit.modules"]
transforms = "science.transforms"
diagnostics = "science.diagnostics"
```

The key is the section header a config may write.
The value is the dotted path conduit imports.

The group name has to be quoted, because TOML would otherwise read `conduit.modules` as a nested table.
It is also why the group is `conduit.modules` and not `conduit-modules`: entry-point group names are specified as dotted Python identifiers, and a hyphen is not one.

Reinstall the package (`uv pip install -e .`) for a new entry point to take effect — the metadata is written at install time, not read from the source tree.

## What conduit does with it

Entry points are read from installed metadata, so nothing of yours is imported while conduit is looking.
The value is handled as a string until a config actually names the section, and a package that registers twenty modules costs a config that uses one of them nothing for the other nineteen.

Two rules are enforced at the point a config is parsed:

- **A registered name cannot shadow a built-in.** `node` is conduit's own, generated from the config's `[[node]]` and `[[resample]]` entries. Registering it fails, naming your package.
- **Two packages cannot register the same name.** Rather than pick one, conduit fails naming both packages and both modules. A config can get past it by writing an explicit `_import_path`, which always wins.

A section that carries `_import_path` never consults the registry at all, so installing your package cannot change the meaning of a config that already says where its code lives.

## Check it took

`--dry-run` names the package behind every section resolved this way:

```
$ conduit run --dry-run pipeline.toml
Dry run for pipeline.toml
  ✓ config parsed; [diagnostics] provided by science: science.diagnostics
  ...
```

`conduit run` logs the same line to the `conduit.pipeline` logger at `INFO`.
A user reading either one can see which installed package supplied the code, which a bare `[diagnostics]` header does not tell them.

To see the whole registry without running a pipeline:

```python
from conduit.importing import discover_registered_modules

discover_registered_modules()
# {'diagnostics': RegisteredModule(section='diagnostics',
#                                  import_path='science.diagnostics',
#                                  distribution='science')}
```

That result is cached for the life of the process.
If you install a package into a running interpreter — a notebook, mostly — call `discover_registered_modules.cache_clear()` before expecting to see it.

## Naming

Section headers share one flat space across the registry and every config that uses it, so pick names a pipeline author would not want for their own local module.
`diagnostics` is a reasonable name for a package to claim; `nodes` is not.

Keyword-only parameters are flatter still: they merge into a single namespace across every section in a config, so two of your modules cannot both declare `threshold`.
Prefixing (`diagnostics_threshold`) is worth doing from the start in a package other people will combine with their own modules.

## Where next

- [Bring your own module](../guides/nodes/bring-your-own-module.md) — the authoring conventions your modules follow, which registration does not change.
- [Configuration reference](../reference/configuration.md#how-a-section-finds-its-module) — the resolution order, in one table.
