"""initial_schema_payment_events_db

Revision ID: 9a82c6d3b654
Revises:
Create Date: 2025-11-10 14:53:38.657990

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9a82c6d3b654'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Create all tables for payment_events_db."""

    # 1. Create payment_events table (Event Store - append-only)
    op.create_table(
        'payment_events',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('aggregate_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('aggregate_type', sa.String(length=50), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('event_data', sa.LargeBinary(), nullable=False),  # Protobuf serialized
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('sequence_number', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', name='payment_events_event_id_key'),
        sa.UniqueConstraint('aggregate_id', 'sequence_number', name='unique_aggregate_sequence'),
        sa.CheckConstraint('sequence_number > 0', name='check_sequence_positive')
    )

    # Indexes for payment_events
    op.create_index('idx_aggregate_events', 'payment_events', ['aggregate_id', 'sequence_number'])
    op.create_index('idx_event_type_created', 'payment_events', ['event_type', sa.text('created_at DESC')])
    op.create_index('idx_created_at', 'payment_events', [sa.text('created_at DESC')])

    # 2. Create outbox table (Transactional Outbox Pattern)
    # Note: Using BYTEA for payload (protobuf messages) as per spec feedback
    op.create_table(
        'outbox',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('aggregate_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('message_type', sa.String(length=100), nullable=False),
        sa.Column('payload', sa.LargeBinary(), nullable=False),  # Protobuf serialized (was JSONB in original spec)
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('processed_at', sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Partial index for unprocessed outbox entries (efficient!)
    op.create_index(
        'idx_unprocessed',
        'outbox',
        ['created_at'],
        postgresql_where=sa.text('processed_at IS NULL')
    )

    # 3. Create auth_request_state table (Read Model)
    op.create_table(
        'auth_request_state',
        sa.Column('auth_request_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('restaurant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('payment_token', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),

        # Result fields (populated by worker)
        sa.Column('processor_auth_id', sa.String(length=255), nullable=True),
        sa.Column('processor_name', sa.String(length=50), nullable=True),
        sa.Column('authorized_amount_cents', sa.BigInteger(), nullable=True),
        sa.Column('authorization_code', sa.String(length=100), nullable=True),

        # Denial details
        sa.Column('denial_code', sa.String(length=50), nullable=True),
        sa.Column('denial_reason', sa.Text(), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('completed_at', sa.TIMESTAMP(), nullable=True),

        # Metadata
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb")),

        # Event sourcing bookkeeping
        sa.Column('last_event_sequence', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('last_event_id', postgresql.UUID(as_uuid=True), nullable=True),

        sa.PrimaryKeyConstraint('auth_request_id'),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'AUTHORIZED', 'DENIED', 'FAILED', 'VOIDED', 'EXPIRED')",
            name='check_status'
        )
    )

    # Indexes for auth_request_state
    op.create_index('idx_restaurant_created', 'auth_request_state', ['restaurant_id', sa.text('created_at DESC')])
    op.create_index(
        'idx_status',
        'auth_request_state',
        ['status'],
        postgresql_where=sa.text("status IN ('PENDING', 'PROCESSING')")
    )
    op.create_index('idx_payment_token', 'auth_request_state', ['payment_token'])
    op.create_index(
        'idx_completed_at',
        'auth_request_state',
        [sa.text('completed_at DESC')],
        postgresql_where=sa.text('completed_at IS NOT NULL')
    )

    # Create trigger function for auto-updating updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
           NEW.updated_at = NOW();
           RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create trigger for auth_request_state
    op.execute("""
        CREATE TRIGGER update_auth_request_state_updated_at
            BEFORE UPDATE ON auth_request_state
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    """)

    # 4. Create restaurant_payment_configs table
    op.create_table(
        'restaurant_payment_configs',
        sa.Column('restaurant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('config_version', sa.String(length=50), nullable=False),
        sa.Column('processor_name', sa.String(length=50), nullable=False),
        sa.Column('processor_config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),

        sa.PrimaryKeyConstraint('restaurant_id'),
        sa.CheckConstraint(
            "processor_name IN ('stripe', 'chase', 'worldpay')",
            name='check_processor'
        )
    )

    # Index for active configs
    op.create_index(
        'idx_active_configs',
        'restaurant_payment_configs',
        ['is_active'],
        postgresql_where=sa.text('is_active = true')
    )

    # Insert seed data for testing (single restaurant with Stripe)
    op.execute("""
        INSERT INTO restaurant_payment_configs (restaurant_id, config_version, processor_name, processor_config, updated_at)
        VALUES (
            '00000000-0000-0000-0000-000000000001'::UUID,
            'v1',
            'stripe',
            '{"stripe_api_key": "sk_test_placeholder", "statement_descriptor": "TEST RESTAURANT"}'::JSONB,
            NOW()
        );
    """)

    # 5. Create auth_idempotency_keys table
    op.create_table(
        'auth_idempotency_keys',
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column('restaurant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('auth_request_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('expires_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text("NOW() + INTERVAL '24 hours'")),

        sa.PrimaryKeyConstraint('idempotency_key', 'restaurant_id')
    )

    # Index for cleanup of expired keys
    op.create_index('idx_idempotency_expires', 'auth_idempotency_keys', ['expires_at'])

    # 6. Create auth_processing_locks table
    op.create_table(
        'auth_processing_locks',
        sa.Column('auth_request_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('worker_id', sa.String(length=255), nullable=False),
        sa.Column('locked_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('expires_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text("NOW() + INTERVAL '30 seconds'")),

        sa.PrimaryKeyConstraint('auth_request_id'),
        sa.CheckConstraint('expires_at > locked_at', name='check_expires_after_locked')
    )

    # Index for cleanup of expired locks
    op.create_index('idx_lock_expires', 'auth_processing_locks', ['expires_at'])


def downgrade() -> None:
    """Downgrade schema - Drop all tables."""

    # Drop tables in reverse order
    op.drop_table('auth_processing_locks')
    op.drop_table('auth_idempotency_keys')
    op.drop_table('restaurant_payment_configs')

    # Drop trigger and function for auth_request_state
    op.execute('DROP TRIGGER IF EXISTS update_auth_request_state_updated_at ON auth_request_state;')
    op.execute('DROP FUNCTION IF EXISTS update_updated_at_column();')

    op.drop_table('auth_request_state')
    op.drop_table('outbox')
    op.drop_table('payment_events')
