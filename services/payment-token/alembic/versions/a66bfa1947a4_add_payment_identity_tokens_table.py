"""add_payment_identity_tokens_table

Revision ID: a66bfa1947a4
Revises: 25d03b185558
Create Date: 2025-11-23 21:56:31.750187

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a66bfa1947a4'
down_revision: Union[str, Sequence[str], None] = '25d03b185558'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'payment_identity_tokens',
        sa.Column('payment_token_guid', sa.String(length=64), nullable=False, comment='Unique payment token identifier (e.g., pit_<uuid>)'),
        sa.Column('hmac', sa.String(length=128), nullable=False, comment='HMAC hash for secure lookup'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Token creation timestamp'),
        sa.PrimaryKeyConstraint('payment_token_guid')
    )
    op.create_index('idx_payment_identity_tokens_hmac', 'payment_identity_tokens', ['hmac'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_payment_identity_tokens_hmac', table_name='payment_identity_tokens')
    op.drop_table('payment_identity_tokens')
