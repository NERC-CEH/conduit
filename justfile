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

# Export a single example notebook to docs/examples/.
export example:
  # Export to Markdown file
  marimo-md-export "examples/{{example}}.py" "docs/examples/{{example}}.md" \
    --html-output docs/examples/{{example}}-notebook.html --overflow scroll

# Export all notebooks in examples/ to docs/examples/.
export-all:
  just export getting_started
  just export unit_safe_pipelines
