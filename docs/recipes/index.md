---
title: Recipes
icon: lucide/book-open
---

# Recipes

A recipe is a complete pipeline you can read end to end: the data, the node module, the config, and the run.
The [guides](../guides/nodes/bring-your-own-module.md) answer "how do I do X?" one piece at a time; a recipe shows a whole task at once.

Each one lives in its own directory under [`recipes/`](https://github.com/NERC-CEH/conduit/tree/main/recipes) and holds a node module, a `config.toml`, a generator for synthetic inputs, and a marimo notebook that runs the pipeline.
The test suite executes every recipe, and so does the documentation build, so nothing here can drift away from the library without something failing.

To run one without cloning the repository:

```sh
uvx marimo edit --sandbox recipes/pipeline_101/demo.py
```

## Available

- **[Pipeline 101](pipeline-101.md)** — the smallest pipeline with every moving part: one input, one imported node, one inline node, one output. Start here. There is also a [notebook walkthrough](pipeline-101-demo.md) of the same pipeline through the Python API.
- **[Flux processing](flux-pipeline.md)** — an annotated eddy-covariance pipeline with unit conversion, temporal resampling, and a deliberately broken config that fails the contract check. The [notebook version](flux-pipeline-demo.md) adds plots.

## Planned

- **Land-cover classification** — a gridded classification pipeline over multi-band inputs.
- **Nowcasting** — a short-horizon forecast with temporal resampling.

If there is a pattern you would like to see worked through, [open an issue](https://github.com/NERC-CEH/conduit/issues).
