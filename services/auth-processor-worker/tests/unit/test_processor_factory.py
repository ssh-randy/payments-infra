"""Unit tests for processor factory."""

import pytest

from auth_processor_worker.processors import (
    MockProcessor,
    PaymentProcessor,
    ProcessorFactory,
    StripeProcessor,
    get_processor,
)


class TestProcessorFactoryCreation:
    """Tests for creating processor instances."""

    def test_create_stripe_processor(self):
        """Test creating a Stripe processor instance."""
        processor = ProcessorFactory.create_processor(
            "stripe",
            processor_config={"api_key": "sk_test_123", "timeout_seconds": 15},
        )

        assert isinstance(processor, StripeProcessor)
        assert processor.api_key == "sk_test_123"
        assert processor.timeout_seconds == 15

    def test_create_mock_processor(self):
        """Test creating a mock processor instance."""
        processor = ProcessorFactory.create_processor("mock")

        assert isinstance(processor, MockProcessor)

    def test_create_processor_case_insensitive(self):
        """Test that processor names are case-insensitive."""
        processor_lower = ProcessorFactory.create_processor(
            "stripe", processor_config={"api_key": "sk_test_123", "timeout_seconds": 10}
        )
        processor_upper = ProcessorFactory.create_processor(
            "STRIPE", processor_config={"api_key": "sk_test_123", "timeout_seconds": 10}
        )
        processor_mixed = ProcessorFactory.create_processor(
            "StRiPe", processor_config={"api_key": "sk_test_123", "timeout_seconds": 10}
        )

        assert isinstance(processor_lower, StripeProcessor)
        assert isinstance(processor_upper, StripeProcessor)
        assert isinstance(processor_mixed, StripeProcessor)

    def test_create_unknown_processor_raises_error(self):
        """Test that creating an unknown processor raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            ProcessorFactory.create_processor("unknown_processor")

        assert "Unknown processor: unknown_processor" in str(exc_info.value)
        assert "Available processors:" in str(exc_info.value)

    def test_create_processor_with_default_config(self):
        """Test creating processor with default config from settings."""
        # This will use the config from settings (or defaults if not set)
        processor = ProcessorFactory.create_processor("stripe")

        assert isinstance(processor, StripeProcessor)
        # Should have default values from settings


class TestProcessorFactoryRegistry:
    """Tests for processor registration."""

    def test_list_processors(self):
        """Test listing available processors."""
        processors = ProcessorFactory.list_processors()

        assert "stripe" in processors
        assert "mock" in processors
        assert isinstance(processors, list)
        assert processors == sorted(processors)  # Should be sorted

    def test_register_new_processor(self):
        """Test registering a new processor type."""

        class CustomProcessor(PaymentProcessor):
            async def authorize(self, payment_data, amount_cents, currency, config):
                pass

        # Register the custom processor
        ProcessorFactory.register_processor("custom", CustomProcessor)

        # Verify it's in the list
        assert "custom" in ProcessorFactory.list_processors()

        # Verify we can create it
        processor = ProcessorFactory.create_processor("custom", processor_config={})
        assert isinstance(processor, CustomProcessor)

        # Clean up - unregister it
        ProcessorFactory._PROCESSORS.pop("custom")

    def test_register_invalid_processor_raises_error(self):
        """Test that registering a non-PaymentProcessor class raises TypeError."""

        class NotAProcessor:
            pass

        with pytest.raises(TypeError) as exc_info:
            ProcessorFactory.register_processor("invalid", NotAProcessor)

        assert "must inherit from PaymentProcessor" in str(exc_info.value)


class TestGetProcessorConvenienceFunction:
    """Tests for the get_processor convenience function."""

    def test_get_processor_default(self):
        """Test get_processor with no arguments defaults to Stripe."""
        processor = get_processor()

        assert isinstance(processor, StripeProcessor)

    def test_get_processor_with_name(self):
        """Test get_processor with specific processor name."""
        processor = get_processor("mock")

        assert isinstance(processor, MockProcessor)

    def test_get_processor_with_config(self):
        """Test get_processor with custom config."""
        processor = get_processor(
            "stripe",
            processor_config={"api_key": "sk_test_custom", "timeout_seconds": 20},
        )

        assert isinstance(processor, StripeProcessor)
        assert processor.api_key == "sk_test_custom"
        assert processor.timeout_seconds == 20

    def test_get_processor_none_name_uses_default(self):
        """Test that None processor name defaults to Stripe."""
        processor = get_processor(processor_name=None)

        assert isinstance(processor, StripeProcessor)


class TestProcessorFactoryExtensibility:
    """Tests for future processor extensibility."""

    def test_factory_supports_multiple_processors(self):
        """Test that factory can create different processor types."""
        stripe_processor = ProcessorFactory.create_processor(
            "stripe", processor_config={"api_key": "sk_test_123", "timeout_seconds": 10}
        )
        mock_processor = ProcessorFactory.create_processor("mock")

        assert isinstance(stripe_processor, StripeProcessor)
        assert isinstance(mock_processor, MockProcessor)
        assert stripe_processor is not mock_processor

    def test_all_registered_processors_inherit_from_base(self):
        """Test that all registered processors inherit from PaymentProcessor."""
        for processor_name in ProcessorFactory.list_processors():
            processor_class = ProcessorFactory._PROCESSORS[processor_name]
            assert issubclass(processor_class, PaymentProcessor)
