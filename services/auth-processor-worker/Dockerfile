FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry

# Copy shared dependencies first
COPY shared/python/payments_proto/ /tmp/payments_proto/

# Copy dependency files
COPY services/auth-processor-worker/pyproject.toml ./
COPY services/auth-processor-worker/poetry.lock* ./

# Install payments_proto package and other dependencies
RUN poetry config virtualenvs.create false \
    && pip install /tmp/payments_proto/ \
    && poetry install --no-interaction --no-ansi --no-root

# Copy application code
COPY services/auth-processor-worker/src/ ./
COPY services/auth-processor-worker/config.yaml ./config.yaml

# Copy entrypoint script
COPY services/auth-processor-worker/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# Health check (checks if worker process is running)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ps aux | grep -v grep | grep python || exit 1

# Run the worker
CMD ["./entrypoint.sh"]
