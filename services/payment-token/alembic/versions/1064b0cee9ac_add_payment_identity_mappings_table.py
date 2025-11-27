"""add_payment_identity_mappings_table

Revision ID: 1064b0cee9ac
Revises: 25d03b185558
Create Date: 2025-11-26 15:46:47.344291

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1064b0cee9ac'
down_revision: Union[str, Sequence[str], None] = '25d03b185558'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'payment_identity_mappings',
        sa.Column('payment_identity_token', sa.String(length=64), nullable=False,
                  comment='Identity token ID in format pi_<uuid>'),
        sa.Column('card_hash', sa.String(length=64), nullable=False,
                  comment='HMAC-SHA256 hash of card_number + cardholder_name'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=False,
                  comment='Mapping creation timestamp'),
        sa.Column('last_used_at', sa.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=False,
                  comment='Last time this identity was used'),
        sa.PrimaryKeyConstraint('payment_identity_token'),
        sa.UniqueConstraint('card_hash', name='uq_card_hash')
    )
    op.create_index('idx_card_hash', 'payment_identity_mappings', ['card_hash'])
    op.create_index('idx_created_at', 'payment_identity_mappings', ['created_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_created_at', table_name='payment_identity_mappings')
    op.drop_index('idx_card_hash', table_name='payment_identity_mappings')
    op.drop_table('payment_identity_mappings')
