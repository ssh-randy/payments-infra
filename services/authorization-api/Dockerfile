FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry

# Copy shared dependencies first
COPY shared/python/payments_proto/ /tmp/payments_proto/

# Copy dependency files
COPY services/authorization-api/pyproject.toml ./
COPY services/authorization-api/poetry.lock* ./

# Install payments_proto package and other dependencies
RUN poetry config virtualenvs.create false \
    && pip install /tmp/payments_proto/ \
    && poetry install --no-interaction --no-ansi --no-root

# Copy and install migrations dependencies
COPY infrastructure/migrations/pyproject.toml infrastructure/migrations/poetry.lock* ./migrations/
RUN cd migrations && poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi --no-root && cd ..

# Copy Alembic configuration and migrations
COPY infrastructure/migrations ./migrations

# Copy application code
COPY services/authorization-api/src/authorization_api ./authorization_api

# Copy entrypoint script
COPY services/authorization-api/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# Expose port
EXPOSE 8000

# Run the application
CMD ["./entrypoint.sh"]
