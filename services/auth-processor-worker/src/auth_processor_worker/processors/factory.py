"""
Processor factory for creating payment processor instances.

This module provides configuration-based processor selection, allowing
the worker to dynamically choose the correct processor (Stripe, Chase,
Worldpay, etc.) based on restaurant configuration.
"""

from typing import Any

import structlog

from auth_processor_worker.config import settings
from auth_processor_worker.processors.base import PaymentProcessor
from auth_processor_worker.processors.mock_processor import MockProcessor
from auth_processor_worker.processors.stripe_processor import StripeProcessor

logger = structlog.get_logger(__name__)


class ProcessorFactory:
    """
    Factory for creating payment processor instances.

    Supports configuration-based processor selection to enable:
    - Multiple payment processors (Stripe, Chase, Worldpay)
    - Per-restaurant processor routing
    - Easy addition of new processors
    """

    # Registry of available processors
    _PROCESSORS: dict[str, type[PaymentProcessor]] = {
        "stripe": StripeProcessor,
        "mock": MockProcessor,
        # Future processors will be added here:
        # "chase": ChaseProcessor,
        # "worldpay": WorldpayProcessor,
    }

    @classmethod
    def create_processor(
        cls,
        processor_name: str,
        processor_config: dict[str, Any] | None = None,
    ) -> PaymentProcessor:
        """
        Create a payment processor instance by name.

        Args:
            processor_name: Name of the processor (e.g., "stripe", "chase")
            processor_config: Optional processor-specific configuration.
                            If not provided, uses settings from global config.

        Returns:
            PaymentProcessor instance ready to authorize payments

        Raises:
            ValueError: If processor_name is not registered

        Examples:
            # Using global config
            processor = ProcessorFactory.create_processor("stripe")

            # Using custom config
            processor = ProcessorFactory.create_processor(
                "stripe",
                processor_config={"api_key": "sk_test_...", "timeout_seconds": 15}
            )
        """
        processor_name_lower = processor_name.lower()

        if processor_name_lower not in cls._PROCESSORS:
            available = ", ".join(cls._PROCESSORS.keys())
            raise ValueError(
                f"Unknown processor: {processor_name}. "
                f"Available processors: {available}"
            )

        processor_class = cls._PROCESSORS[processor_name_lower]

        # If no config provided, use settings from environment
        if processor_config is None:
            processor_config = cls._get_default_config(processor_name_lower)

        logger.info(
            "processor_created",
            processor_name=processor_name_lower,
            processor_class=processor_class.__name__,
        )

        # Instantiate the processor with its config
        # Different processors may have different initialization parameters
        if processor_name_lower == "stripe":
            return processor_class(
                api_key=processor_config.get("api_key", ""),
                timeout_seconds=processor_config.get("timeout_seconds", 10),
            )
        elif processor_name_lower == "mock":
            return processor_class()
        else:
            # Generic instantiation for future processors
            # May need to be customized per processor
            return processor_class(**processor_config)

    @classmethod
    def _get_default_config(cls, processor_name: str) -> dict[str, Any]:
        """
        Get default configuration for a processor from settings.

        Args:
            processor_name: Name of the processor

        Returns:
            Configuration dictionary with processor settings
        """
        if processor_name == "stripe":
            return {
                "api_key": settings.stripe.api_key,
                "timeout_seconds": settings.stripe.timeout_seconds,
            }
        elif processor_name == "mock":
            return {}
        else:
            # Future processors will load their config here
            return {}

    @classmethod
    def register_processor(
        cls,
        name: str,
        processor_class: type[PaymentProcessor],
    ) -> None:
        """
        Register a new processor type.

        This allows adding processors dynamically without modifying this file.
        Useful for plugins or custom processor implementations.

        Args:
            name: Name to register the processor under (e.g., "chase")
            processor_class: PaymentProcessor subclass to register

        Example:
            ProcessorFactory.register_processor("chase", ChaseProcessor)
        """
        if not issubclass(processor_class, PaymentProcessor):
            raise TypeError(
                f"{processor_class.__name__} must inherit from PaymentProcessor"
            )

        cls._PROCESSORS[name.lower()] = processor_class
        logger.info(
            "processor_registered",
            processor_name=name.lower(),
            processor_class=processor_class.__name__,
        )

    @classmethod
    def list_processors(cls) -> list[str]:
        """
        Get list of available processor names.

        Returns:
            List of registered processor names
        """
        return sorted(cls._PROCESSORS.keys())


def get_processor(
    processor_name: str | None = None,
    processor_config: dict[str, Any] | None = None,
) -> PaymentProcessor:
    """
    Convenience function to create a payment processor.

    This is the recommended way to get a processor instance in the worker.

    Args:
        processor_name: Name of processor (defaults to "stripe")
        processor_config: Optional processor-specific config

    Returns:
        PaymentProcessor instance

    Examples:
        # Use default Stripe processor
        processor = get_processor()

        # Use specific processor
        processor = get_processor("stripe")

        # Use processor with custom config
        processor = get_processor(
            "stripe",
            processor_config={"api_key": "sk_test_...", "timeout_seconds": 15}
        )
    """
    if processor_name is None:
        processor_name = "stripe"  # Default processor

    return ProcessorFactory.create_processor(processor_name, processor_config)
