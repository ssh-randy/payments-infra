"""Database connection and session management for Payment Token Service."""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import QueuePool

from payment_token.config import settings

# Base class for all ORM models
Base = declarative_base()


def create_db_engine(database_url: str | None = None) -> Engine:
    """
    Create a SQLAlchemy engine with connection pooling.

    Args:
        database_url: PostgreSQL connection URL. If None, uses settings.database_url

    Returns:
        Configured SQLAlchemy engine
    """
    url = database_url or settings.database_url

    engine = create_engine(
        url,
        poolclass=QueuePool,
        pool_size=10,  # Number of connections to keep open
        max_overflow=20,  # Additional connections when pool is full
        pool_pre_ping=True,  # Verify connections before using
        pool_recycle=3600,  # Recycle connections after 1 hour
        echo=settings.debug,  # Log SQL statements in debug mode
    )

    # Set PostgreSQL-specific settings for security
    @event.listens_for(engine, "connect")
    def set_postgresql_pragma(dbapi_conn, connection_record):  # type: ignore
        cursor = dbapi_conn.cursor()
        cursor.execute("SET timezone='UTC'")
        cursor.execute("SET statement_timeout='30000'")  # 30 second timeout
        cursor.close()

    return engine


# Global engine and session factory (initialized by application startup)
engine = create_db_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.

    Usage:
        with get_db_session() as session:
            session.query(PaymentToken).filter_by(payment_token='pt_123').first()

    Automatically commits on success, rolls back on exception.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for database sessions.

    Usage:
        @app.get("/example")
        def example(db: Session = Depends(get_db)):
            return db.query(PaymentToken).all()

    Yields:
        Database session
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db(engine: Engine | None = None) -> None:
    """
    Initialize database schema (create all tables).

    WARNING: This should only be used for testing. In production, use Alembic migrations.

    Args:
        engine: Optional engine to use. If None, uses global engine.
    """
    target_engine = engine or globals()['engine']
    Base.metadata.create_all(bind=target_engine)


def drop_all_tables(engine: Engine | None = None) -> None:
    """
    Drop all tables in the database.

    WARNING: This is destructive and should only be used for testing.

    Args:
        engine: Optional engine to use. If None, uses global engine.
    """
    target_engine = engine or globals()['engine']
    Base.metadata.drop_all(bind=target_engine)


def reset_db(engine: Engine | None = None) -> None:
    """
    Reset database (drop all tables and recreate them).

    WARNING: This is destructive and should only be used for testing.

    Args:
        engine: Optional engine to use. If None, uses global engine.
    """
    drop_all_tables(engine)
    init_db(engine)
