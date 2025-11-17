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
COPY services/payment-token/pyproject.toml ./
COPY services/payment-token/poetry.lock* ./

# Install payments_proto package and other dependencies
RUN poetry config virtualenvs.create false \
    && pip install /tmp/payments_proto/ \
    && poetry install --no-interaction --no-ansi --no-root

# Copy Alembic configuration and migrations
COPY services/payment-token/alembic.ini ./alembic.ini
COPY services/payment-token/alembic/ ./alembic/

# Copy application code
COPY services/payment-token/src/ ./

# Copy entrypoint script
COPY services/payment-token/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# Expose port
EXPOSE 8000

# Run the application
CMD ["./entrypoint.sh"]
