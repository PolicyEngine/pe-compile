.PHONY: install test format lint clean

install:
	pip install -e ".[dev]"

test:
	pytest -v

test-cov:
	pytest --cov=pe_compile --cov-report=term-missing --cov-report=html

format:
	black pe_compile tests
	ruff check --fix pe_compile tests

lint:
	black --check pe_compile tests
	ruff check pe_compile tests

clean:
	rm -rf build dist *.egg-info
	rm -rf .pytest_cache .coverage htmlcov coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
