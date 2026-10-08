---
title: Recipes
icon: lucide/book-open
---

# Recipes

A recipe is a complete pipeline you can read end to end: the data, the node module, the config, and the run.

Each lives in its own directory under [`recipes/`](https://github.com/NERC-CEH/conduit/tree/main/recipes), with a node module, a `config.toml`, a synthetic-data generator, and a marimo notebook that runs the pipeline.
The tests and the docs build both execute every recipe, so they stay in step with the library.

To run one without cloning the repository:

```sh
uvx marimo edit --sandbox recipes/pipeline_101/demo.py
```

## Available

- **[Pipeline 101](pipeline-101.md)** — the smallest pipeline with every moving part: one input, one imported node, one inline node, one output. Start here.
- **[Flux processing](flux-pipeline.md)** — an annotated eddy-covariance pipeline with unit conversion, temporal resampling, and plots of the products.

## Planned

- **Land-cover classification** — a gridded classification pipeline over multi-band inputs.
- **Nowcasting** — a short-horizon forecast with temporal resampling.

If there is a pattern you would like to see worked through, [open an issue](https://github.com/NERC-CEH/conduit/issues).
