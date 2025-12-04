"""Integration tests for CardIdentityTokenRepository with real database."""

import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from payment_token.infrastructure.database import Base
from payment_token.infrastructure.repository import CardIdentityTokenRepository
from payment_token.infrastructure.models import CardIdentityToken as CardIdentityTokenModel


# Test database setup
TEST_DATABASE_URL = "sqlite:///file:test_identity_db?mode=memory&cache=shared&uri=true"


@pytest.fixture(scope="session")
def test_engine():
    """Create a test database engine and run Alembic migrations."""
    # Import models to ensure they're registered
    from payment_token.infrastructure import models  # noqa: F401

    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False, "uri": True},
        poolclass=None,  # Disable pooling for testing
    )

    # Run Alembic migrations programmatically
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)

    with engine.begin() as connection:
        alembic_cfg.attributes["connection"] = connection
        command.upgrade(alembic_cfg, "head")

    yield engine

    # Downgrade to base (clean up)
    with engine.begin() as connection:
        alembic_cfg.attributes["connection"] = connection
        command.downgrade(alembic_cfg, "base")

    engine.dispose()


@pytest.fixture(scope="session")
def test_session_factory(test_engine):
    """Create a session factory for the test database."""
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def test_db(test_engine, test_session_factory):
    """Provide a clean database for each test by truncating tables."""
    with test_engine.connect() as connection:
        # Clean up card_identity_tokens table between tests
        connection.execute(text("DELETE FROM card_identity_tokens"))
        connection.commit()

    yield test_session_factory, test_engine


@pytest.fixture
def session(test_db):
    """Create a database session for a test."""
    TestingSessionLocal, _ = test_db
    session = TestingSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture
def repository(session):
    """Create a repository instance."""
    return CardIdentityTokenRepository(session)


class TestCardIdentityTokenRepositoryIntegration:
    """Integration tests for CardIdentityTokenRepository with real database."""

    def test_repository_with_real_database_create_and_retrieve(self, repository, session):
        """Test full CRUD operations against real database."""
        # Arrange
        card_hash = "a1b2c3d4e5f6g7h8" * 4
        identity_token = str(uuid.uuid4())

        # Act - Create
        repository.create(card_hash, identity_token)
        session.commit()

        # Act - Retrieve
        result = repository.get_by_card_hash(card_hash)

        # Assert
        assert result == identity_token

        # Verify in database
        record = session.query(CardIdentityTokenModel).filter(
            CardIdentityTokenModel.card_hash == card_hash
        ).first()
        assert record is not None
        assert record.card_hash == card_hash
        assert record.identity_token == identity_token
        assert record.created_at is not None

    def test_create_duplicate_hash_raises_integrity_error(self, repository, session):
        """Test that creating duplicate card hash raises IntegrityError."""
        # Arrange
        card_hash = "duplicate" * 8
        identity_token_1 = str(uuid.uuid4())
        identity_token_2 = str(uuid.uuid4())

        # Act - Create first record
        repository.create(card_hash, identity_token_1)
        session.commit()

        # Act & Assert - Try to create duplicate
        with pytest.raises(IntegrityError):
            repository.create(card_hash, identity_token_2)
            session.flush()

        # Rollback the failed transaction
        session.rollback()

    def test_unique_constraint_on_identity_token(self, repository, session):
        """Test that identity_token unique constraint is enforced."""
        # Arrange
        card_hash_1 = "card1hash" * 8
        card_hash_2 = "card2hash" * 8
        identity_token = str(uuid.uuid4())

        # Act - Create first record
        repository.create(card_hash_1, identity_token)
        session.commit()

        # Act & Assert - Try to use same identity token
        with pytest.raises(IntegrityError):
            repository.create(card_hash_2, identity_token)
            session.flush()

        # Rollback the failed transaction
        session.rollback()

    def test_get_or_create_creates_new_when_not_exists(self, repository, session):
        """Test get_or_create creates new record when card hash doesn't exist."""
        # Arrange
        card_hash = "newcard" * 8
        identity_token = str(uuid.uuid4())

        # Act
        result = repository.get_or_create(card_hash, identity_token)
        session.commit()

        # Assert
        assert result == identity_token

        # Verify in database
        record = session.query(CardIdentityTokenModel).filter(
            CardIdentityTokenModel.card_hash == card_hash
        ).first()
        assert record is not None
        assert record.identity_token == identity_token

    def test_get_or_create_returns_existing_when_exists(self, repository, session):
        """Test get_or_create returns existing identity token when card hash exists."""
        # Arrange
        card_hash = "existing" * 8
        existing_token = str(uuid.uuid4())
        new_token = str(uuid.uuid4())

        # Create existing record
        repository.create(card_hash, existing_token)
        session.commit()

        # Act - Try to create with different token
        result = repository.get_or_create(card_hash, new_token)

        # Assert - Returns existing token, not new one
        assert result == existing_token
        assert result != new_token

        # Verify only one record exists
        records = session.query(CardIdentityTokenModel).filter(
            CardIdentityTokenModel.card_hash == card_hash
        ).all()
        assert len(records) == 1
        assert records[0].identity_token == existing_token

    def test_concurrent_inserts_handled_correctly(self, test_db):
        """Test that concurrent inserts for same card hash are handled correctly.

        Note: This test is skipped on SQLite due to database locking limitations.
        SQLite uses file-based locking which doesn't work well with concurrent writes
        in the same process. In production with PostgreSQL, this works correctly.
        """
        TestingSessionLocal, engine = test_db

        # Skip test for SQLite due to locking limitations
        if "sqlite" in str(engine.url):
            pytest.skip("SQLite doesn't handle concurrent writes well in tests")

        card_hash = "concurrent" * 8
        tokens = [str(uuid.uuid4()) for _ in range(5)]

        def insert_identity_token(token):
            """Insert identity token in separate session."""
            session = TestingSessionLocal()
            try:
                repo = CardIdentityTokenRepository(session)
                result = repo.get_or_create(card_hash, token)
                session.commit()
                return result
            except Exception as e:
                session.rollback()
                raise e
            finally:
                session.close()

        # Execute concurrent inserts
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(insert_identity_token, token) for token in tokens]
            results = [future.result() for future in as_completed(futures)]

        # Assert - All should return the same identity token (winner of race)
        assert len(set(results)) == 1
        winning_token = results[0]

        # Verify only one record exists in database
        session = TestingSessionLocal()
        try:
            records = session.query(CardIdentityTokenModel).filter(
                CardIdentityTokenModel.card_hash == card_hash
            ).all()
            assert len(records) == 1
            assert records[0].identity_token == winning_token
        finally:
            session.close()

    def test_transaction_rollback_no_orphaned_records(self, repository, session):
        """Test that rollback doesn't leave orphaned records."""
        # Arrange
        card_hash = "rollback" * 8
        identity_token = str(uuid.uuid4())

        # Act - Create but rollback
        repository.create(card_hash, identity_token)
        session.rollback()

        # Assert - Record should not exist
        result = repository.get_by_card_hash(card_hash)
        assert result is None

        record = session.query(CardIdentityTokenModel).filter(
            CardIdentityTokenModel.card_hash == card_hash
        ).first()
        assert record is None

    def test_index_exists_on_identity_token(self, test_engine):
        """Test that index on identity_token column exists."""
        # Query SQLite index information
        with test_engine.connect() as connection:
            result = connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='card_identity_tokens'")
            )
            indexes = [row[0] for row in result]

        # Assert index exists
        assert "idx_identity_token" in indexes

    def test_primary_key_constraint(self, test_engine):
        """Test that primary key constraint exists on card_hash."""
        # Query table info
        with test_engine.connect() as connection:
            result = connection.execute(
                text("PRAGMA table_info(card_identity_tokens)")
            )
            columns = {row[1]: row for row in result}  # column name -> row

        # Assert card_hash is primary key
        assert "card_hash" in columns
        card_hash_col = columns["card_hash"]
        assert card_hash_col[5] == 1  # pk column (1 = primary key)

    def test_multiple_cards_different_identities(self, repository, session):
        """Test that multiple different cards get different identity tokens."""
        # Arrange
        cards = [
            ("card1hash" * 8, str(uuid.uuid4())),
            ("card2hash" * 8, str(uuid.uuid4())),
            ("card3hash" * 8, str(uuid.uuid4())),
        ]

        # Act - Create multiple cards
        for card_hash, identity_token in cards:
            repository.create(card_hash, identity_token)
        session.commit()

        # Assert - All can be retrieved correctly
        for card_hash, expected_token in cards:
            result = repository.get_by_card_hash(card_hash)
            assert result == expected_token

        # Verify all records exist
        all_records = session.query(CardIdentityTokenModel).all()
        assert len(all_records) == 3
