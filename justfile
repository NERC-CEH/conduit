_: lint typecheck test

# Format and lint the package using ruff, and lint the examples using marimo.
lint:
  ruff format
  ruff check --fix
  marimo check examples/

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
  pytest --cov=satterc --cov-report=term-missing --cov-fail-under=90

# Build the documentation using Zensical.
docs:
  zensical build

# Export a single example notebook to docs/Examples/.
export example:
  # Export to Markdown file
  marimo-md-export "examples/{{example}}.py" "docs/examples/{{example}}.md" \
    --html-output docs/examples/{{example}}-notebook.html --overflow scroll

# Export all notebooks in examples/ to docs/Examples/.
export-all:
  just export my_first_pipeline
  just export soil_moisture
  just export pft_parameters
  just export full_pipeline
