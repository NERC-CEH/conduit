_: lint typecheck test

# Format and lint the package using ruff, and lint the examples using marimo.
lint:
  ruff format
  ruff check --fix
  marimo check --fix examples/

# Variant of `lint` that doesn't cause any changes to files.
lint-check:
  ruff format --check
  ruff check
  marimo check examples/

# Run static type checker.
typecheck:
  pyright

# Run the full test suite.
test:
  pytest --verbose # --log-cli-level=INFO

# Run tests with coverage report.
test-cov:
  pytest --cov=conduit --cov-report=term-missing --cov-fail-under=90

# Build the documentation using Zensical.
docs:
  zensical build

# Export a marimo example notebook to a docs page (markdown + interactive HTML).
export notebook dest:
  marimo-md-export "examples/{{notebook}}.py" "docs/{{dest}}.md" \
    --html-output "docs/{{dest}}-notebook.html" --overflow scroll

# Export all example notebooks to their docs pages.
export-all:
  just export units_and_contracts get-started/units-and-contracts
  just export drive_from_python guides/drive-from-python
