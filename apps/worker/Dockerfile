FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml /app/pyproject.toml
COPY packages/observability /app/packages/observability
COPY apps/worker /app/apps/worker

WORKDIR /app/apps/worker
RUN uv sync --no-cache

CMD ["uv", "run", "python", "-m", "relay_worker.main"]
