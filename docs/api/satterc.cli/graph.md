# `satterc.cli.graph`

Visualise a pipeline defined in a configuration file.

## Usage

```sh
satterc graph <CONFIG_FILE> [OPTIONS]
```

## Arguments

| Argument | Description |
|----------|-------------|
| `CONFIG_FILE` | Path to a TOML configuration file |

## Options

| Flag | Description |
|------|-------------|
| `--output`, `-o` | Name of output file (default: `pipeline`) |
| `--style`, `-s` | Optional TOML file customising the DAG styling (see `satterc.cli.graph_style`) |
| `--allow-overrides` | Allow later modules to override earlier ones |
| `--png` | Convert to PNG format |
| `--pdf` | Convert to PDF format |

## API Documentation

::: satterc.cli.graph
