FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml /app/pyproject.toml
COPY packages/observability /app/packages/observability
COPY apps/api /app/apps/api

WORKDIR /app/apps/api
RUN uv sync --no-cache

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "relay_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--app-dir", "src"]
