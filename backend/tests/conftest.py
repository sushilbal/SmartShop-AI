import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator, Any
from unittest.mock import MagicMock

from config.config import DATABASE_URL # Your main DB URL
from src.main import app, get_db, get_qdrant_db_client # Import your FastAPI app and dependencies
from src.models import Base # Import your SQLAlchemy Base

# --- Test Database Setup ---
# For testing, it's best to use a separate database.
# You can modify DATABASE_URL or use a different one for tests.
# For simplicity, we'll use the same structure but on a test DB.
# Ensure your test DB exists or is created before running tests.
TEST_DATABASE_URL = DATABASE_URL.replace("smartshop_db", "test_smartshop_db")

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session", autouse=True)
def create_test_database():
    """
    Creates all tables in the test database before tests run,
    and drops them after tests are done.
    """
    Base.metadata.create_all(bind=engine) # Create tables
    yield
    Base.metadata.drop_all(bind=engine) # Drop tables

@pytest.fixture(scope="function")
def db_session() -> Generator[Session, Any, None]:
    """
    Provides a database session for each test function.
    Rolls back transactions after each test to ensure isolation.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="function")
def mock_qdrant_client() -> MagicMock:
    """
    Provides a mock Qdrant client.
    """
    client = MagicMock()
    # You can configure mock methods if needed, e.g., client.upsert.return_value = None
    client.upsert.return_value = None
    client.delete.return_value = None
    client.get_collections.return_value = MagicMock(collections=[]) # Mock an empty list of collections
    client.create_collection.return_value = True
    return client

@pytest.fixture(scope="function")
def client(db_session: Session, mock_qdrant_client: MagicMock) -> Generator[TestClient, Any, None]:
    """
    Provides a TestClient for the FastAPI application,
    with overridden dependencies for the database and Qdrant client.
    """

    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()

    def override_get_qdrant_db_client():
        return mock_qdrant_client

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_qdrant_db_client] = override_get_qdrant_db_client

    with TestClient(app) as test_client:
        yield test_client

    # Clean up overrides after tests
    app.dependency_overrides.clear()
