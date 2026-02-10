.PHONY: install lint format test coverage docs clean install-tool uninstall-tool docker-build docker-test check-all

# Install all dependencies including dev extras
install:
	uv sync --all-extras

lint:
	uv run ruff check src tests
	uv run mypy src

format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

test:
	uv run pytest

coverage:
	uv run pytest --cov=src --cov-report=html --cov-report=term

docs:
	uv run mkdocs serve

clean:
	rm -rf dist build *.egg-info
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -rf htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +

install-tool:
	uv tool install .

uninstall-tool:
	uv tool uninstall termseries

docker-build:
	docker compose build

# Verify the Docker container runs correctly
docker-test:
	docker compose run --rm app

# Run all verification targets in order (excludes docs, install-tool, uninstall-tool)
check-all: install format lint test docker-build docker-test clean
	@echo "All checks passed!"
