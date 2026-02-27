.PHONY: install lint format test coverage docs clean install-tool uninstall-tool docker-build docker-run docker-tui docker-test check-all

# Allow: make docker-run yahoo TSLA AAPL
# Allow: make docker-tui yahoo TSLA AAPL
ifeq (docker-run,$(firstword $(MAKECMDGOALS)))
  ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
  $(eval $(ARGS):;@:)
else ifeq (docker-tui,$(firstword $(MAKECMDGOALS)))
  ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
  $(eval $(ARGS):;@:)
endif

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
	uv tool install --reinstall .

uninstall-tool:
	uv tool uninstall termseries

docker-build:
	docker compose build

docker-run:
	docker compose run --rm app $(ARGS)

docker-tui:
	docker compose run --rm app -i $(ARGS)

# Verify the Docker container runs correctly
docker-test:
	docker compose run --rm app --help

# Run all verification targets in order (excludes docs, install-tool, uninstall-tool)
check-all: install format lint test docker-build docker-test clean
	@echo "All checks passed!"
