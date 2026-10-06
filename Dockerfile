# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install dependencies first so that editing source code does not invalidate this layer.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY frontend ./frontend
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --frozen --no-dev

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
