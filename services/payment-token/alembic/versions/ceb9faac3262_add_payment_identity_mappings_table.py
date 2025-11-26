"""Add payment_identity_mappings table for loyalty card recognition

Revision ID: ceb9faac3262
Revises: 25d03b185558
Create Date: 2025-11-24 16:04:09.197606

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'ceb9faac3262'
down_revision: Union[str, Sequence[str], None] = '25d03b185558'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create payment_identity_mappings table
    op.create_table(
        'payment_identity_mappings',
        sa.Column('card_hash', sa.String(length=64), nullable=False, comment='HMAC-SHA256 hex output (64 chars)'),
        sa.Column('payment_identity_token', UUID(as_uuid=False), nullable=False, comment='Stable UUID for this card'),
        sa.Column('first_seen_at', sa.TIMESTAMP(timezone=True), nullable=False, comment='When first encountered'),
        sa.Column('last_seen_at', sa.TIMESTAMP(timezone=True), nullable=False, comment='Most recent usage'),
        sa.Column('usage_count', sa.Integer(), nullable=False, server_default='1', comment='How many times seen'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Record creation timestamp'),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Record update timestamp'),
        sa.PrimaryKeyConstraint('card_hash')
    )

    # Create indexes
    op.create_index('idx_payment_identity_token', 'payment_identity_mappings', ['payment_identity_token'])
    op.create_index('idx_last_seen_at', 'payment_identity_mappings', ['last_seen_at'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes first
    op.drop_index('idx_last_seen_at', 'payment_identity_mappings')
    op.drop_index('idx_payment_identity_token', 'payment_identity_mappings')

    # Drop table
    op.drop_table('payment_identity_mappings')
