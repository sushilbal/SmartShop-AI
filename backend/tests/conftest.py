import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import OperationalError, ProgrammingError
from typing import Generator, Any
from unittest.mock import MagicMock

from config.config import DATABASE_URL # Your main DB URL
from src.main import app # Import your FastAPI app
from src.dependencies import get_db, get_qdrant_db_client # Import dependencies
from src.models import Base # Import your SQLAlchemy Base

# For robust URL manipulation
from urllib.parse import urlparse, urlunparse

# --- Test Database Setup ---
# For testing, it's best to use a separate database.
# Ensure your test DB exists or is created before running tests.

TEST_DB_NAME = "test_smartshop_db"

# Construct TEST_DATABASE_URL robustly
parsed_original_url = urlparse(DATABASE_URL)
TEST_DATABASE_URL = parsed_original_url._replace(path=f"/{TEST_DB_NAME}").geturl()

# URL for connecting to a maintenance database (e.g., postgres) to create the test database
# This assumes you have a 'postgres' database or similar default maintenance DB.
MAINTENANCE_DB_URL = parsed_original_url._replace(path="/postgres").geturl()

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session", autouse=True)
def create_test_database():
    """
    Ensures the test database exists and creates all tables before tests run.
    Drops all tables after tests are done.
    The test database itself is not dropped by this fixture by default.
    """
    maintenance_engine = create_engine(MAINTENANCE_DB_URL, isolation_level="AUTOCOMMIT")
    
    try:
        with maintenance_engine.connect() as conn:
            # Check if the test database exists (PostgreSQL specific)
            result = conn.execute(text(f"SELECT 1 FROM pg_database WHERE datname = '{TEST_DB_NAME}'"))
            db_exists = result.scalar_one_or_none()

            if not db_exists:
                conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
                print(f"INFO: Test database '{TEST_DB_NAME}' created.")
            else:
                print(f"INFO: Test database '{TEST_DB_NAME}' already exists.")
    except OperationalError as e:
        print(f"CRITICAL: Could not connect to maintenance database '{MAINTENANCE_DB_URL}' to create test database. Error: {e}")
        print("Ensure your PostgreSQL server is running and the maintenance database is accessible.")
        raise
    except ProgrammingError as e: # Catch other DB errors during creation
        print(f"WARNING: Error while trying to create database '{TEST_DB_NAME}'. It might already exist or there's a permission issue. Error: {e}")
    finally:
        maintenance_engine.dispose()

    # Now, create tables in the test_smartshop_db using the main 'engine'
    Base.metadata.create_all(bind=engine) 
    yield
    Base.metadata.drop_all(bind=engine)

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
