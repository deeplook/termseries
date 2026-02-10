# Contributing

## Development Setup

1. Clone the repository
2. Install dependencies: `uv sync --all-extras`
3. Install pre-commit hooks: `uv run pre-commit install`

## Code Style

This project uses:
- `ruff` for linting and formatting
- `mypy` for type checking

Run `make lint` to check, `make format` to auto-fix.

## Testing

Run `make test` or `make coverage` for coverage report.

## Pull Requests

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run `make lint` and `make test`
5. Submit a pull request
