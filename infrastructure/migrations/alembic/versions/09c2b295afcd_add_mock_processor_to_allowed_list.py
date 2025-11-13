"""add_mock_processor_to_allowed_list

Revision ID: 09c2b295afcd
Revises: 9a82c6d3b654
Create Date: 2025-11-11 14:50:21.396999

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '09c2b295afcd'
down_revision: Union[str, Sequence[str], None] = '9a82c6d3b654'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 'mock' processor to allowed processor names for testing."""
    # Drop the old constraint
    op.drop_constraint('check_processor', 'restaurant_payment_configs', type_='check')

    # Create new constraint that includes 'mock'
    op.create_check_constraint(
        'check_processor',
        'restaurant_payment_configs',
        "processor_name IN ('stripe', 'chase', 'worldpay', 'mock')"
    )


def downgrade() -> None:
    """Remove 'mock' processor from allowed processor names."""
    # Drop the constraint with 'mock'
    op.drop_constraint('check_processor', 'restaurant_payment_configs', type_='check')

    # Restore original constraint without 'mock'
    op.create_check_constraint(
        'check_processor',
        'restaurant_payment_configs',
        "processor_name IN ('stripe', 'chase', 'worldpay')"
    )
