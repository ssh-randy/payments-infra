"""add card identity tokens table

Revision ID: 04ffb16fe291
Revises: 25d03b185558
Create Date: 2025-12-03 12:50:01.051423

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '04ffb16fe291'
down_revision: Union[str, Sequence[str], None] = '25d03b185558'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create card_identity_tokens table."""
    op.create_table(
        'card_identity_tokens',
        sa.Column(
            'card_hash',
            sa.String(length=64),
            nullable=False,
            comment='HMAC-SHA256 hash (hex) of card_number|cardholder_name'
        ),
        sa.Column(
            'identity_token',
            postgresql.UUID(as_uuid=False),
            nullable=False,
            comment='Identity token UUID for this card'
        ),
        sa.Column(
            'created_at',
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='First time this card was seen'
        ),
        sa.PrimaryKeyConstraint('card_hash', name='pk_card_identity_tokens'),
        sa.UniqueConstraint('identity_token', name='uq_card_identity_tokens_identity_token')
    )

    # Create index for reverse lookups
    op.create_index(
        'idx_identity_token',
        'card_identity_tokens',
        ['identity_token']
    )


def downgrade() -> None:
    """Drop card_identity_tokens table."""
    op.drop_index('idx_identity_token', table_name='card_identity_tokens')
    op.drop_table('card_identity_tokens')
