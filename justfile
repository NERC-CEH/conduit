_: lint typecheck test

# Format and lint the package using ruff.
lint:
  ruff format
  ruff check --fix

# Variant of `lint` that doesn't cause any changes to files.
lint-check:
  ruff format --check
  ruff check

# Run static type checker.
typecheck:
  pyright

# Run the full test suite.
test:
  pytest --verbose # --log-cli-level=INFO

# Run tests with coverage report.
test-cov:
  pytest --cov=conduit --cov-report=term-missing --cov-fail-under=90

# Export executable notebooks and build the documentation using Zensical.
docs: docs-examples
  uv run zensical build

# Export the executable recipe notebooks with their rendered outputs.
docs-examples:
  uv run marimo-md-export examples/flux_pipeline/demo.py docs/recipes/flux-pipeline-demo.md --timeout 120
