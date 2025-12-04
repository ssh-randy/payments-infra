"""Unit tests for CardIdentityTokenRepository."""

from unittest.mock import Mock, MagicMock
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from payment_token.infrastructure.repository import CardIdentityTokenRepository
from payment_token.infrastructure.models import CardIdentityToken as CardIdentityTokenModel


class TestCardIdentityTokenRepository:
    """Tests for CardIdentityTokenRepository."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return Mock()

    @pytest.fixture
    def repository(self, mock_session):
        """Create a repository with mock session."""
        return CardIdentityTokenRepository(mock_session)

    def test_init(self, mock_session):
        """Test repository initialization."""
        repo = CardIdentityTokenRepository(mock_session)
        assert repo.session == mock_session

    def test_get_by_card_hash_found(self, repository, mock_session):
        """Test retrieving identity token when card hash exists."""
        # Arrange
        card_hash = "a1b2c3d4e5f6g7h8" * 4  # 64 char hash
        identity_token = "550e8400-e29b-41d4-a716-446655440000"

        mock_record = Mock()
        mock_record.identity_token = identity_token

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_record
        mock_session.query.return_value = mock_query

        # Act
        result = repository.get_by_card_hash(card_hash)

        # Assert
        assert result == identity_token
        mock_session.query.assert_called_once_with(CardIdentityTokenModel)
        mock_query.filter.assert_called_once()

    def test_get_by_card_hash_not_found(self, repository, mock_session):
        """Test retrieving identity token when card hash doesn't exist."""
        # Arrange
        card_hash = "a1b2c3d4e5f6g7h8" * 4

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        mock_session.query.return_value = mock_query

        # Act
        result = repository.get_by_card_hash(card_hash)

        # Assert
        assert result is None

    def test_create_success(self, repository, mock_session):
        """Test successfully creating a new identity token mapping."""
        # Arrange
        card_hash = "a1b2c3d4e5f6g7h8" * 4
        identity_token = "550e8400-e29b-41d4-a716-446655440000"

        # Act
        repository.create(card_hash, identity_token)

        # Assert
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

        # Verify the model was created with correct attributes
        added_model = mock_session.add.call_args[0][0]
        assert isinstance(added_model, CardIdentityTokenModel)
        assert added_model.card_hash == card_hash
        assert added_model.identity_token == identity_token
        assert isinstance(added_model.created_at, datetime)

    def test_create_duplicate_raises_integrity_error(self, repository, mock_session):
        """Test that creating duplicate card hash raises IntegrityError."""
        # Arrange
        card_hash = "a1b2c3d4e5f6g7h8" * 4
        identity_token = "550e8400-e29b-41d4-a716-446655440000"

        # Make flush raise IntegrityError (simulating duplicate key)
        mock_session.flush.side_effect = IntegrityError("duplicate key", None, None)

        # Act & Assert
        with pytest.raises(IntegrityError):
            repository.create(card_hash, identity_token)

    def test_get_or_create_creates_new(self, repository, mock_session):
        """Test get_or_create creates new mapping when card hash doesn't exist."""
        # Arrange
        card_hash = "a1b2c3d4e5f6g7h8" * 4
        identity_token = "550e8400-e29b-41d4-a716-446655440000"

        # flush succeeds (no duplicate)
        mock_session.flush.side_effect = None

        # Act
        result = repository.get_or_create(card_hash, identity_token)

        # Assert
        assert result == identity_token
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()
        mock_session.rollback.assert_not_called()

    def test_get_or_create_returns_existing(self, repository, mock_session):
        """Test get_or_create returns existing identity token when card hash exists."""
        # Arrange
        card_hash = "a1b2c3d4e5f6g7h8" * 4
        new_identity_token = "550e8400-e29b-41d4-a716-446655440000"
        existing_identity_token = "660e8400-e29b-41d4-a716-446655440001"

        # First flush raises IntegrityError (duplicate key)
        mock_session.flush.side_effect = IntegrityError("duplicate key", None, None)

        # Query returns existing record
        mock_existing = Mock()
        mock_existing.identity_token = existing_identity_token

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_existing
        mock_session.query.return_value = mock_query

        # Act
        result = repository.get_or_create(card_hash, new_identity_token)

        # Assert
        assert result == existing_identity_token  # Returns existing, not new
        mock_session.add.assert_called_once()
        mock_session.rollback.assert_called_once()
        mock_session.query.assert_called_once_with(CardIdentityTokenModel)

    def test_get_or_create_handles_race_condition(self, repository, mock_session):
        """Test get_or_create handles concurrent insert race condition."""
        # Arrange
        card_hash = "a1b2c3d4e5f6g7h8" * 4
        identity_token_1 = "550e8400-e29b-41d4-a716-446655440000"
        identity_token_2 = "660e8400-e29b-41d4-a716-446655440001"

        # Simulate race condition: flush raises IntegrityError
        mock_session.flush.side_effect = IntegrityError("duplicate key", None, None)

        # Query returns the other request's token
        mock_existing = Mock()
        mock_existing.identity_token = identity_token_2

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_existing
        mock_session.query.return_value = mock_query

        # Act
        result = repository.get_or_create(card_hash, identity_token_1)

        # Assert
        assert result == identity_token_2  # Returns winner of race
        mock_session.rollback.assert_called_once()

    def test_get_or_create_raises_on_missing_record(self, repository, mock_session):
        """Test get_or_create raises RuntimeError if record exists but cannot be retrieved."""
        # Arrange
        card_hash = "a1b2c3d4e5f6g7h8" * 4
        identity_token = "550e8400-e29b-41d4-a716-446655440000"

        # Flush raises IntegrityError but query returns None (should never happen)
        mock_session.flush.side_effect = IntegrityError("duplicate key", None, None)

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        mock_session.query.return_value = mock_query

        # Act & Assert
        with pytest.raises(RuntimeError, match="Card hash exists but could not be retrieved"):
            repository.get_or_create(card_hash, identity_token)

    def test_card_hash_truncation_in_logs(self, repository, mock_session, caplog):
        """Test that card hashes are truncated in log messages."""
        import logging
        caplog.set_level(logging.DEBUG)

        # Arrange
        card_hash = "a1b2c3d4e5f6g7h8" * 4  # 64 chars
        identity_token = "550e8400-e29b-41d4-a716-446655440000"

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        mock_session.query.return_value = mock_query

        # Act
        repository.get_by_card_hash(card_hash)

        # Assert - verify only first 8 chars appear in logs
        assert "a1b2c3d4" in caplog.text  # First 8 chars
        assert card_hash not in caplog.text  # Full hash should not appear
