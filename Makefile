.PHONY: install test format lint clean docs

install:
	uv pip install -e ".[dev]"

install-uk:
	uv pip install -e ".[dev,uk]"

install-us:
	uv pip install -e ".[dev,us]"

test:
	uv run pytest -v

test-cov:
	uv run pytest --cov=pe_compile --cov-report=term-missing --cov-report=html

format:
	uv run black pe_compile tests
	uv run ruff check --fix pe_compile tests

lint:
	uv run black --check pe_compile tests
	uv run ruff check pe_compile tests

docs:
	cd docs && myst build --html

docs-serve:
	cd docs && myst start

benchmark:
	uv run python benchmark.py

clean:
	rm -rf build dist *.egg-info
	rm -rf .pytest_cache .coverage htmlcov coverage.xml
	rm -rf docs/_build
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
