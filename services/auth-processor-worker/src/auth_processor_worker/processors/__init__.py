"""
Payment processor integrations.

This module contains all payment processor implementations:
- base.PaymentProcessor: Abstract interface that all processors must implement
- stripe_processor.StripeProcessor: Production Stripe integration
- mock_processor.MockProcessor: Mock processor for testing (mirrors Stripe behavior)
- factory: Processor factory for configuration-based processor selection

IMPORTANT - MAINTAINING SYNC BETWEEN STRIPE AND MOCK:
The MockProcessor is designed to mirror StripeProcessor's behavior for testing.
When making changes to StripeProcessor, review MockProcessor to ensure:
1. Test card behaviors match Stripe's test cards
2. Response structures remain consistent
3. Error handling patterns are aligned
4. Metadata fields are synchronized

See mock_processor.py for detailed sync points.
"""

from auth_processor_worker.processors.base import PaymentProcessor
from auth_processor_worker.processors.factory import ProcessorFactory, get_processor
from auth_processor_worker.processors.mock_processor import MockProcessor
from auth_processor_worker.processors.stripe_processor import StripeProcessor

__all__ = [
    "PaymentProcessor",
    "StripeProcessor",
    "MockProcessor",
    "ProcessorFactory",
    "get_processor",
]
