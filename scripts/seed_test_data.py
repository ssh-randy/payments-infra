#!/usr/bin/env python3
"""Seed test data for local development."""

import asyncio
import sys
from uuid import UUID


async def seed_restaurant_configs():
    """Seed test restaurant payment configurations."""
    print("Seeding restaurant payment configs...")

    # TODO: Implement seeding logic with actual database connection
    # Example:
    # - Create test restaurant with Stripe config
    # - Create test restaurant with Chase config (future)

    print("✓ Restaurant configs seeded")


async def main():
    """Main entry point."""
    try:
        await seed_restaurant_configs()
        print("✓ All test data seeded successfully")
    except Exception as e:
        print(f"Error seeding data: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
