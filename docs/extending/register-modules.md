---
title: Register modules from a package
icon: lucide/package-plus
---

# Register modules from a package

A package of node modules can register them with conduit, so a config names one by its section header alone:

```toml
[diagnostics]
threshold = 0.3
```

instead of repeating the import path in every config:

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

The key is the section header a config may write, and the value is the dotted module path conduit imports.
Quote the group name, or TOML reads `conduit.modules` as a nested table.

Entry points are written at install time, so reinstall the package (`uv pip install -e .`) after adding one.

## What conduit does with it

conduit reads entry points from installed metadata and imports a registered module only when a config names its section.

Three rules apply when a config is parsed:

- **A registered name cannot shadow a built-in section** (`node`, `resample`, `inputs`, `outputs`, `validation`, `cache`, `blocking`, `subset`, `annotations`, `point_dim`).
  Such a registration is ignored with a warning naming your package, so it cannot break configs belonging to people who merely have your package installed.
- **The value must be a plain dotted module path.**
  A `module:attribute` value or a `.py` path is ignored with a warning; a `.py` path would resolve against the *user's* config directory.
- **Two packages cannot register the same name.**
  conduit refuses that one name, naming both packages, and everything else keeps working.
  A config resolves the clash by writing an explicit `_import_path`.

A section with an `_import_path` never consults the registry, so installing your package cannot change the meaning of a config that already says where its code lives.

## Check it took

`--dry-run` names the package behind every section resolved this way:

```
$ conduit run --dry-run pipeline.toml
Dry run for pipeline.toml
  ✓ config parsed; [diagnostics] provided by science: science.diagnostics
  ...
```

`conduit run` logs the same line to the `conduit.pipeline` logger at `INFO`, so users can see which package supplied the code behind a bare `[diagnostics]` header.

To list the whole registry:

```python
from conduit.importing import discover_registered_modules

discover_registered_modules()
# {'diagnostics': RegisteredModule(section='diagnostics',
#                                  import_path='science.diagnostics',
#                                  distribution='science')}
```

The result is cached for the life of the process; after installing a package into a running interpreter, call `conduit.importing.clear_registry_cache()`.

## Naming

Registered names share one space with every section name in every config, so pick names a pipeline author would not want for a local module: `diagnostics` is reasonable, `nodes` is not.

Keyword-only parameters [share one namespace](../guides/nodes/bring-your-own-module.md#parameter-names-share-one-namespace) across every section in a config, so two of your modules cannot both declare `threshold`, nor can yours and a user's.
Prefix them from the start (`diagnostics_threshold`).
