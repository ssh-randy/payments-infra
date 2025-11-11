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

# Copy dependency files
COPY services/payment-token/pyproject.toml ./
COPY services/payment-token/poetry.lock* ./

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# Copy protobuf files from shared directory
COPY shared/python/payments_proto/ ./payments_proto/

# Create symlink for protobuf imports to work
RUN ln -s /app/payments_proto/payments /app/payments

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
