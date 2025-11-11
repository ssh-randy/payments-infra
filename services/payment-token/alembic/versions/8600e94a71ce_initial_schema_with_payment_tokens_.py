"""Initial schema with payment_tokens, encryption_keys, idempotency_keys, and audit_log tables

Revision ID: 8600e94a71ce
Revises:
Create Date: 2025-11-10 10:52:45.450411

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '8600e94a71ce'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create payment_tokens table
    op.create_table(
        'payment_tokens',
        sa.Column('payment_token', sa.String(length=64), nullable=False, comment='Token ID in format pt_<uuid>'),
        sa.Column('restaurant_id', UUID(as_uuid=False), nullable=False, comment='Restaurant UUID'),
        sa.Column('encrypted_payment_data', sa.LargeBinary(), nullable=False, comment='Payment data encrypted with service key'),
        sa.Column('encryption_key_version', sa.String(length=50), nullable=False, comment='Version of encryption key used'),
        sa.Column('device_token', sa.String(length=255), nullable=False, comment='Device identifier used for original encryption'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Token creation timestamp'),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=False, comment='Token expiration timestamp'),
        sa.Column('metadata', sa.JSON(), nullable=True, comment='Non-sensitive metadata (card_brand, last4, etc.)'),
        sa.PrimaryKeyConstraint('payment_token')
    )
    op.create_index('idx_restaurant_created', 'payment_tokens', ['restaurant_id', 'created_at'])
    op.create_index('idx_expires_at', 'payment_tokens', ['expires_at'])
    op.create_index(op.f('ix_payment_tokens_restaurant_id'), 'payment_tokens', ['restaurant_id'])

    # Create token_idempotency_keys table
    op.create_table(
        'token_idempotency_keys',
        sa.Column('idempotency_key', sa.String(length=255), nullable=False, comment='Client-provided idempotency key'),
        sa.Column('restaurant_id', UUID(as_uuid=False), nullable=False, comment='Restaurant UUID'),
        sa.Column('payment_token', sa.String(length=64), nullable=False, comment='Payment token created for this idempotency key'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Idempotency key creation timestamp'),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=False, comment='Idempotency key expiration (24 hours)'),
        sa.PrimaryKeyConstraint('idempotency_key', 'restaurant_id')
    )
    op.create_index('idx_idempotency_expires_at', 'token_idempotency_keys', ['expires_at'])

    # Create encryption_keys table
    op.create_table(
        'encryption_keys',
        sa.Column('key_version', sa.String(length=50), nullable=False, comment='Encryption key version identifier'),
        sa.Column('kms_key_id', sa.String(length=255), nullable=False, comment='AWS KMS key ARN'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Key version creation timestamp'),
        sa.Column('is_active', sa.Boolean(), nullable=False, comment='Whether this key is currently active'),
        sa.Column('retired_at', sa.TIMESTAMP(timezone=True), nullable=True, comment='When this key was retired'),
        sa.PrimaryKeyConstraint('key_version')
    )

    # Create decrypt_audit_log table
    op.create_table(
        'decrypt_audit_log',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='Audit log entry ID'),
        sa.Column('payment_token', sa.String(length=64), nullable=False, comment='Token that was decrypted'),
        sa.Column('restaurant_id', UUID(as_uuid=False), nullable=False, comment='Restaurant UUID'),
        sa.Column('requesting_service', sa.String(length=100), nullable=False, comment='Service that requested decryption (e.g., auth-processor-worker)'),
        sa.Column('request_id', sa.String(length=255), nullable=False, comment='Correlation/request ID for tracing'),
        sa.Column('success', sa.Boolean(), nullable=False, comment='Whether decryption succeeded'),
        sa.Column('error_code', sa.String(length=50), nullable=True, comment='Error code if decryption failed'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Audit log entry creation timestamp'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_token_created', 'decrypt_audit_log', ['payment_token', 'created_at'])
    op.create_index(op.f('ix_decrypt_audit_log_created_at'), 'decrypt_audit_log', ['created_at'])
    op.create_index(op.f('ix_decrypt_audit_log_payment_token'), 'decrypt_audit_log', ['payment_token'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('decrypt_audit_log')
    op.drop_table('encryption_keys')
    op.drop_table('token_idempotency_keys')
    op.drop_table('payment_tokens')
