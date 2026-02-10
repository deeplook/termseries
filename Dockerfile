FROM python:3.12-slim AS builder

WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy README.md with pyproject.toml because hatchling validates readme exists
COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN uv build

FROM python:3.12-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY --from=builder /app/dist/*.whl /app/

# Install wheel into system Python (venv symlinks break in multi-stage builds)
RUN uv pip install --system /app/*.whl && rm /app/*.whl

ENTRYPOINT ["python", "-m", "termseries"]
