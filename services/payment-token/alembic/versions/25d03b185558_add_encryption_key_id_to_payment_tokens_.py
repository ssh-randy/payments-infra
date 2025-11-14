"""Add encryption_key_id to payment_tokens for API partner key support

Revision ID: 25d03b185558
Revises: 8600e94a71ce
Create Date: 2025-11-13 20:47:26.774211

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '25d03b185558'
down_revision: Union[str, Sequence[str], None] = '8600e94a71ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Use batch operations for SQLite compatibility
    with op.batch_alter_table('payment_tokens', schema=None) as batch_op:
        # Add encryption_key_id column to payment_tokens table
        batch_op.add_column(
            sa.Column(
                'encryption_key_id',
                sa.String(length=255),
                nullable=True,
                comment='Key ID used for encryption (e.g., "primary", "ak_{uuid}", "bdk_{id}")'
            )
        )

        # Create index for key_id lookups (useful for key rotation queries)
        batch_op.create_index(
            'idx_payment_tokens_key_id',
            ['encryption_key_id']
        )

        # Make device_token nullable (not used in API partner key flow)
        batch_op.alter_column(
            'device_token',
            nullable=True,
            existing_type=sa.String(length=255),
            comment='Device identifier used for original encryption (null for API partner keys)'
        )


def downgrade() -> None:
    """Downgrade schema."""
    # Use batch operations for SQLite compatibility
    with op.batch_alter_table('payment_tokens', schema=None) as batch_op:
        # Revert device_token to NOT NULL
        batch_op.alter_column(
            'device_token',
            nullable=False,
            existing_type=sa.String(length=255),
            comment='Device identifier used for original encryption'
        )

        # Drop index first
        batch_op.drop_index('idx_payment_tokens_key_id')

        # Drop column
        batch_op.drop_column('encryption_key_id')
