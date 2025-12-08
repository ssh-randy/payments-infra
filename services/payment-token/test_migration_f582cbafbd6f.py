#!/usr/bin/env python3
"""
Test script to verify the saved card fields migration (f582cbafbd6f).

This script validates that:
1. Migration can be applied (upgrade)
2. All columns and indexes are created correctly
3. Migration can be rolled back (downgrade)
4. Backward compatibility is maintained

Run with: python test_migration_f582cbafbd6f.py
Requires: Running PostgreSQL database (use make test-setup)
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from sqlalchemy import create_engine, inspect, text
from alembic import command
from alembic.config import Config


def test_migration_upgrade_downgrade():
    """Test that migration can be applied and rolled back."""

    # Use test database
    database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://postgres:password@localhost:5433/payment_tokens_test"
    )

    print(f"Testing migration with database: {database_url}")

    # Create Alembic config
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)

    # Create engine for inspection
    engine = create_engine(database_url)
    inspector = inspect(engine)

    try:
        print("\n=== Testing Migration Upgrade ===")

        # Run migration upgrade to head
        command.upgrade(alembic_cfg, "head")
        print("✓ Migration upgrade successful")

        # Verify columns were added
        print("\n=== Verifying Columns ===")
        columns = {col['name']: col for col in inspector.get_columns('payment_tokens')}

        expected_columns = {
            'customer_id': 'UUID',
            'is_saved': 'BOOLEAN',
            'card_label': 'VARCHAR(255)',
            'is_default': 'BOOLEAN',
            'last_used_at': 'TIMESTAMP'
        }

        for col_name in expected_columns:
            if col_name in columns:
                print(f"✓ Column '{col_name}' exists")
            else:
                raise AssertionError(f"Column '{col_name}' was not created!")

        # Verify is_saved and is_default have default values
        print("\n=== Verifying Column Defaults ===")
        is_saved_col = columns['is_saved']
        is_default_col = columns['is_default']

        # Check if defaults are set (may vary by database driver representation)
        print(f"  is_saved default: {is_saved_col.get('default')}")
        print(f"  is_default default: {is_default_col.get('default')}")

        # Verify indexes were created
        print("\n=== Verifying Indexes ===")
        indexes = inspector.get_indexes('payment_tokens')
        index_names = {idx['name'] for idx in indexes}

        expected_indexes = {
            'idx_customer_saved_tokens',
            'idx_customer_default_token'
        }

        for idx_name in expected_indexes:
            if idx_name in index_names:
                print(f"✓ Index '{idx_name}' exists")
            else:
                raise AssertionError(f"Index '{idx_name}' was not created!")

        # Test backward compatibility: insert a token without saved card fields
        print("\n=== Testing Backward Compatibility ===")
        with engine.connect() as conn:
            result = conn.execute(text("""
                INSERT INTO payment_tokens (
                    payment_token,
                    restaurant_id,
                    encrypted_payment_data,
                    encryption_key_version,
                    expires_at,
                    metadata
                )
                VALUES (
                    'pt_test_legacy_token',
                    '550e8400-e29b-41d4-a716-446655440000',
                    E'\\\\x0123456789abcdef',
                    'v1',
                    NOW() + INTERVAL '24 hours',
                    '{"card_brand": "visa", "last4": "4242"}'::jsonb
                )
                RETURNING payment_token, is_saved, is_default, customer_id, card_label, last_used_at
            """))
            row = result.fetchone()
            conn.commit()

            print(f"  Inserted token: {row[0]}")
            print(f"  is_saved: {row[1]} (should be False)")
            print(f"  is_default: {row[2]} (should be False)")
            print(f"  customer_id: {row[3]} (should be None)")
            print(f"  card_label: {row[4]} (should be None)")
            print(f"  last_used_at: {row[5]} (should be None)")

            # Verify defaults
            assert row[1] is False, "is_saved should default to False"
            assert row[2] is False, "is_default should default to False"
            assert row[3] is None, "customer_id should be None for legacy tokens"
            print("✓ Legacy token insertion works with correct defaults")

            # Clean up
            conn.execute(text("DELETE FROM payment_tokens WHERE payment_token = 'pt_test_legacy_token'"))
            conn.commit()

        # Test saved card insertion
        print("\n=== Testing Saved Card Insertion ===")
        with engine.connect() as conn:
            result = conn.execute(text("""
                INSERT INTO payment_tokens (
                    payment_token,
                    restaurant_id,
                    customer_id,
                    encrypted_payment_data,
                    encryption_key_version,
                    expires_at,
                    is_saved,
                    card_label,
                    is_default,
                    metadata
                )
                VALUES (
                    'pt_test_saved_card',
                    '550e8400-e29b-41d4-a716-446655440000',
                    '660e8400-e29b-41d4-a716-446655440000',
                    E'\\\\x0123456789abcdef',
                    'v1',
                    '2027-12-31 23:59:59',
                    true,
                    'Test Visa',
                    true,
                    '{"card_brand": "visa", "last4": "4242"}'::jsonb
                )
                RETURNING payment_token, is_saved, is_default, customer_id, card_label
            """))
            row = result.fetchone()
            conn.commit()

            print(f"  Inserted saved card: {row[0]}")
            print(f"  is_saved: {row[1]} (should be True)")
            print(f"  is_default: {row[2]} (should be True)")
            print(f"  customer_id: {row[3]}")
            print(f"  card_label: {row[4]}")

            assert row[1] is True, "is_saved should be True"
            assert row[2] is True, "is_default should be True"
            print("✓ Saved card insertion works correctly")

            # Clean up
            conn.execute(text("DELETE FROM payment_tokens WHERE payment_token = 'pt_test_saved_card'"))
            conn.commit()

        # Test index usage on saved cards
        print("\n=== Testing Index Usage ===")
        with engine.connect() as conn:
            # Use EXPLAIN to verify index is used
            result = conn.execute(text("""
                EXPLAIN SELECT payment_token
                FROM payment_tokens
                WHERE customer_id = '660e8400-e29b-41d4-a716-446655440000'
                  AND restaurant_id = '550e8400-e29b-41d4-a716-446655440000'
                  AND is_saved = true
                ORDER BY created_at DESC
            """))
            explain_output = [row[0] for row in result]
            print("  Query plan:")
            for line in explain_output:
                print(f"    {line}")

            # Check if our index is mentioned (idx_customer_saved_tokens)
            # Note: May not always use index on empty table, but we can verify it exists
            print("✓ Query plan generated (index available for use)")

        print("\n=== Testing Migration Downgrade ===")

        # Downgrade migration
        command.downgrade(alembic_cfg, "-1")
        print("✓ Migration downgrade successful")

        # Verify columns were removed
        print("\n=== Verifying Columns Removed ===")
        columns_after = {col['name'] for col in inspector.get_columns('payment_tokens')}

        for col_name in expected_columns:
            if col_name not in columns_after:
                print(f"✓ Column '{col_name}' removed")
            else:
                raise AssertionError(f"Column '{col_name}' was not removed!")

        # Verify indexes were removed
        print("\n=== Verifying Indexes Removed ===")
        indexes_after = inspector.get_indexes('payment_tokens')
        index_names_after = {idx['name'] for idx in indexes_after}

        for idx_name in expected_indexes:
            if idx_name not in index_names_after:
                print(f"✓ Index '{idx_name}' removed")
            else:
                raise AssertionError(f"Index '{idx_name}' was not removed!")

        # Upgrade again to leave database in correct state
        print("\n=== Restoring Migration ===")
        command.upgrade(alembic_cfg, "head")
        print("✓ Migration restored")

        print("\n" + "=" * 50)
        print("✅ ALL TESTS PASSED")
        print("=" * 50)

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    test_migration_upgrade_downgrade()
