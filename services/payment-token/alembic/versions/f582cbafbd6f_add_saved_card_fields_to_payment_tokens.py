"""Add saved card fields to payment_tokens table

Revision ID: f582cbafbd6f
Revises: 25d03b185558
Create Date: 2025-12-07 21:41:47.865997

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'f582cbafbd6f'
down_revision: Union[str, Sequence[str], None] = '25d03b185558'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add columns and indexes for saved credit card functionality."""
    # Use batch operations for SQLite compatibility
    with op.batch_alter_table('payment_tokens', schema=None) as batch_op:
        # Add customer_id column (UUID, nullable for backward compatibility)
        batch_op.add_column(
            sa.Column(
                'customer_id',
                UUID(as_uuid=False),
                nullable=True,
                comment='Customer UUID - required when is_saved=true'
            )
        )

        # Add is_saved column (BOOLEAN, default FALSE)
        batch_op.add_column(
            sa.Column(
                'is_saved',
                sa.Boolean(),
                nullable=False,
                server_default='false',
                comment='Whether this token represents a saved card'
            )
        )

        # Add card_label column (VARCHAR(255), nullable)
        batch_op.add_column(
            sa.Column(
                'card_label',
                sa.String(length=255),
                nullable=True,
                comment='Optional display name for saved card (e.g., "Personal Visa")'
            )
        )

        # Add is_default column (BOOLEAN, default FALSE)
        batch_op.add_column(
            sa.Column(
                'is_default',
                sa.Boolean(),
                nullable=False,
                server_default='false',
                comment='Whether this is the default payment method for customer+restaurant'
            )
        )

        # Add last_used_at column (TIMESTAMP, nullable)
        batch_op.add_column(
            sa.Column(
                'last_used_at',
                sa.TIMESTAMP(timezone=True),
                nullable=True,
                comment='Timestamp of last successful authorization with this token'
            )
        )

    # Create partial index for saved cards queries
    # Index: (customer_id, restaurant_id, is_saved, created_at DESC) WHERE is_saved = TRUE
    op.create_index(
        'idx_customer_saved_tokens',
        'payment_tokens',
        ['customer_id', 'restaurant_id', 'is_saved', sa.text('created_at DESC')],
        postgresql_where=sa.text('is_saved = TRUE')
    )

    # Create partial index for default card lookup
    # Index: (customer_id, restaurant_id) WHERE is_default = TRUE
    op.create_index(
        'idx_customer_default_token',
        'payment_tokens',
        ['customer_id', 'restaurant_id'],
        postgresql_where=sa.text('is_default = TRUE')
    )


def downgrade() -> None:
    """Downgrade schema - remove saved card columns and indexes."""
    # Drop indexes first
    op.drop_index('idx_customer_default_token', table_name='payment_tokens')
    op.drop_index('idx_customer_saved_tokens', table_name='payment_tokens')

    # Use batch operations for SQLite compatibility
    with op.batch_alter_table('payment_tokens', schema=None) as batch_op:
        # Drop columns in reverse order
        batch_op.drop_column('last_used_at')
        batch_op.drop_column('is_default')
        batch_op.drop_column('card_label')
        batch_op.drop_column('is_saved')
        batch_op.drop_column('customer_id')
