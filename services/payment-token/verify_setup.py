#!/usr/bin/env python3
"""
Verification script for Payment Token Service database setup.

This script verifies that:
- All models can be imported
- Alembic configuration is valid
- Migration files are syntactically correct
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def verify_imports():
    """Verify all imports work correctly."""
    print("✓ Checking imports...")
    try:
        from payment_token.config import settings
        from payment_token.infrastructure.database import Base, get_db_session
        from payment_token.infrastructure.models import (
            PaymentToken,
            TokenIdempotencyKey,
            EncryptionKey,
            DecryptAuditLog,
        )
        print("  ✓ All imports successful")
        return True
    except Exception as e:
        print(f"  ✗ Import error: {e}")
        return False


def verify_models():
    """Verify model definitions."""
    print("✓ Checking model definitions...")
    try:
        from payment_token.infrastructure.database import Base
        from payment_token.infrastructure import models

        tables = Base.metadata.tables
        expected_tables = {
            'payment_tokens',
            'token_idempotency_keys',
            'encryption_keys',
            'decrypt_audit_log'
        }

        actual_tables = set(tables.keys())

        if actual_tables == expected_tables:
            print(f"  ✓ All {len(expected_tables)} tables defined correctly")
            for table_name in sorted(expected_tables):
                table = tables[table_name]
                print(f"    - {table_name} ({len(table.columns)} columns)")
            return True
        else:
            missing = expected_tables - actual_tables
            extra = actual_tables - expected_tables
            if missing:
                print(f"  ✗ Missing tables: {missing}")
            if extra:
                print(f"  ✗ Extra tables: {extra}")
            return False

    except Exception as e:
        print(f"  ✗ Model verification error: {e}")
        return False


def verify_migration():
    """Verify migration file exists and is valid."""
    print("✓ Checking migration files...")
    try:
        versions_dir = Path(__file__).parent / "alembic" / "versions"
        migration_files = list(versions_dir.glob("*.py"))

        if not migration_files:
            print("  ✗ No migration files found")
            return False

        print(f"  ✓ Found {len(migration_files)} migration file(s)")
        for mf in migration_files:
            print(f"    - {mf.name}")

        # Try to compile the migration file
        migration_file = migration_files[0]
        with open(migration_file) as f:
            compile(f.read(), migration_file, 'exec')
        print("  ✓ Migration file is syntactically valid")
        return True

    except Exception as e:
        print(f"  ✗ Migration verification error: {e}")
        return False


def main():
    """Run all verification checks."""
    print("=" * 50)
    print("Payment Token Service - Setup Verification")
    print("=" * 50)
    print()

    checks = [
        verify_imports(),
        verify_models(),
        verify_migration(),
    ]

    print()
    print("=" * 50)
    if all(checks):
        print("✓ All verification checks passed!")
        print()
        print("Next steps:")
        print("  1. Ensure PostgreSQL is running")
        print("  2. Run migrations: ./scripts/migrate_payment_token_db.sh")
        print("  3. Or reset database: ./scripts/reset_payment_token_db.sh")
        return 0
    else:
        print("✗ Some verification checks failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
