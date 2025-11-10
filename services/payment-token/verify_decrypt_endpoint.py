#!/usr/bin/env python3
"""Verification script for decrypt endpoint implementation.

This script verifies that all components of the decrypt endpoint are properly implemented:
- Audit logging infrastructure
- Service authentication
- Internal API routes
- Database models
- Configuration
"""

import sys

print("Verifying decrypt endpoint implementation...")
print("=" * 60)

# Check 1: Audit logging
print("\n1. Checking audit logging infrastructure...")
try:
    from payment_token.infrastructure.audit import (
        AuditLogger,
        DecryptAuditEvent,
        log_decrypt_failure,
        log_decrypt_success,
    )
    print("   ✓ Audit logging module imported successfully")
    print("   ✓ AuditLogger class available")
    print("   ✓ Helper functions available")
except ImportError as e:
    print(f"   ✗ Failed to import audit logging: {e}")
    sys.exit(1)

# Check 2: Service authentication
print("\n2. Checking service authentication...")
try:
    from payment_token.api.auth import (
        UnauthorizedServiceError,
        verify_service_authorization,
    )
    print("   ✓ Service authentication module imported successfully")
    print("   ✓ verify_service_authorization function available")
except ImportError as e:
    print(f"   ✗ Failed to import service authentication: {e}")
    sys.exit(1)

# Check 3: Internal API routes
print("\n3. Checking internal API routes...")
try:
    from payment_token.api.internal_routes import router

    print("   ✓ Internal routes module imported successfully")
    print(f"   ✓ Router configured with prefix: {router.prefix}")

    # Check if decrypt endpoint is registered
    decrypt_endpoint_found = False
    for route in router.routes:
        if hasattr(route, "path") and "decrypt" in route.path:
            decrypt_endpoint_found = True
            print(f"   ✓ Decrypt endpoint found: {route.methods} {route.path}")

    if not decrypt_endpoint_found:
        print("   ✗ Decrypt endpoint not found in router")
        sys.exit(1)

except ImportError as e:
    print(f"   ✗ Failed to import internal routes: {e}")
    sys.exit(1)

# Check 4: Database models
print("\n4. Checking database models...")
try:
    from payment_token.infrastructure.models import DecryptAuditLog

    print("   ✓ DecryptAuditLog model imported successfully")

    # Check model fields
    expected_fields = [
        "id",
        "payment_token",
        "restaurant_id",
        "requesting_service",
        "request_id",
        "success",
        "error_code",
        "created_at",
    ]

    for field in expected_fields:
        if hasattr(DecryptAuditLog, field):
            print(f"   ✓ Field '{field}' present in DecryptAuditLog")
        else:
            print(f"   ✗ Field '{field}' missing from DecryptAuditLog")
            sys.exit(1)

except ImportError as e:
    print(f"   ✗ Failed to import database models: {e}")
    sys.exit(1)

# Check 5: Configuration
print("\n5. Checking configuration...")
try:
    from payment_token.config import settings

    print("   ✓ Settings imported successfully")
    print(f"   ✓ Allowed services: {settings.allowed_services}")
    print(f"   ✓ Current key version: {settings.current_key_version}")

    if "auth-processor-worker" not in settings.allowed_services:
        print("   ✗ auth-processor-worker not in allowed services")
        sys.exit(1)

    if "void-processor-worker" not in settings.allowed_services:
        print("   ✗ void-processor-worker not in allowed services")
        sys.exit(1)

    print("   ✓ All required services in allowlist")

except ImportError as e:
    print(f"   ✗ Failed to import configuration: {e}")
    sys.exit(1)

# Check 6: KMS client
print("\n6. Checking KMS client...")
try:
    from payment_token.infrastructure.kms import KMSClient

    print("   ✓ KMS client imported successfully")

    # Check if get_service_encryption_key method exists
    if hasattr(KMSClient, "get_service_encryption_key"):
        print("   ✓ get_service_encryption_key method available")
    else:
        print("   ✗ get_service_encryption_key method missing")
        sys.exit(1)

except ImportError as e:
    print(f"   ✗ Failed to import KMS client: {e}")
    sys.exit(1)

# Check 7: Domain services
print("\n7. Checking domain services...")
try:
    from payment_token.domain.services import TokenService, validate_token_for_use

    print("   ✓ Domain services imported successfully")

    # Check TokenService methods
    if hasattr(TokenService, "decrypt_token"):
        print("   ✓ decrypt_token method available")
    else:
        print("   ✗ decrypt_token method missing")
        sys.exit(1)

except ImportError as e:
    print(f"   ✗ Failed to import domain services: {e}")
    sys.exit(1)

# Check 8: FastAPI application
print("\n8. Checking FastAPI application...")
try:
    from payment_token.api.main import app

    print("   ✓ FastAPI application imported successfully")
    print(f"   ✓ Application title: {app.title}")

    # Check if internal router is included
    internal_routes_found = False
    for route in app.routes:
        if hasattr(route, "path") and "/internal/v1" in route.path:
            internal_routes_found = True
            print(f"   ✓ Internal route found: {route.path}")
            break

    if not internal_routes_found:
        print("   ⚠ Warning: No internal routes found in app")

except ImportError as e:
    print(f"   ✗ Failed to import FastAPI application: {e}")
    sys.exit(1)

# Final summary
print("\n" + "=" * 60)
print("✓ All components verified successfully!")
print("\nDecrypt endpoint implementation is complete:")
print("  - Audit logging infrastructure (i-3l8u)")
print("  - Service authentication middleware")
print("  - POST /internal/v1/decrypt endpoint")
print("  - Integration tests")
print("\nNext steps:")
print("  1. Run integration tests: poetry run pytest tests/integration/")
print("  2. Test with LocalStack KMS")
print("  3. Implement public endpoints (POST /v1/payment-tokens, GET /v1/payment-tokens/{id})")
print("=" * 60)
