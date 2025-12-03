"""Card Identity Token domain models and repository interface.

This module defines the abstract repository interface for card identity token
persistence following the Dependency Inversion Principle. The domain layer
defines what it needs (this interface), and the infrastructure layer implements it.

This enables:
- Parallel development of domain and infrastructure layers
- Testability through mocking
- Flexibility to swap implementations
"""

from abc import ABC, abstractmethod
from typing import Optional


class ICardIdentityTokenRepository(ABC):
    """Abstract repository for card identity token persistence.

    Defines the contract that infrastructure implementations must follow.
    Domain layer depends on this interface, not concrete implementations.

    The card identity token maps a card hash (HMAC-SHA256 of card data) to a
    stable UUID identity token. This allows the same physical card to be
    recognized across multiple tokenization events while maintaining PCI
    compliance (no PAN storage).
    """

    @abstractmethod
    def get_by_card_hash(self, card_hash: str) -> Optional[str]:
        """Retrieve identity token by card hash.

        Args:
            card_hash: HMAC-SHA256 hash (hex string) of card data.
                      Expected format: 64-character lowercase hex string.

        Returns:
            Identity token UUID string if found, None otherwise.
            UUID format: 8-4-4-4-12 hex characters (e.g., "550e8400-e29b-41d4-a716-446655440000")

        Raises:
            Exception: For database connection errors, query errors, or other
                      infrastructure failures. Concrete implementations should
                      raise specific exceptions appropriate to their storage backend.
        """
        pass

    @abstractmethod
    def create(self, card_hash: str, identity_token: str) -> None:
        """Create new card identity token mapping.

        Args:
            card_hash: HMAC-SHA256 hash (hex string) of card data.
                      Expected format: 64-character lowercase hex string.
            identity_token: UUID string to associate with this card.
                           Expected format: 8-4-4-4-12 hex characters.

        Raises:
            IntegrityError: If card_hash already exists (duplicate key violation).
                           Implementations should raise an IntegrityError or similar
                           constraint violation exception when attempting to insert
                           a duplicate card_hash.
            Exception: For other database errors (connection failures, permission
                      errors, etc.). Concrete implementations should raise specific
                      exceptions appropriate to their storage backend.

        Notes:
            - This method should NOT check for existing card_hash before inserting.
              Let the database enforce uniqueness via constraints.
            - Callers should handle IntegrityError to implement get-or-create logic.
        """
        pass
