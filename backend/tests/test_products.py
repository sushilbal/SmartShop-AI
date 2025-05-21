from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import MagicMock, ANY
import uuid # For generating deterministic UUIDs if needed for Qdrant ID matching

from src.models import ProductDB # Import your DB model
from config.config import VECTOR_DB_COLLECTION_PRODUCTS # Import collection name

# Test data
sample_product_data_create = {
    "product_id": "TESTPROD001",
    "name": "Test Product 1",
    "description": "This is a test product description.",
    "price": 99.99,
    "category": "Test Category",
    "brand": "Test Brand",
    "stock": 100,
    "rating": 4.5
}

updated_product_data_create = {
    "product_id": "TESTPROD001", # Assuming ProductCreate requires product_id
    "name": "Updated Test Product 1",
    "description": "This is an updated test product description.",
    "price": 109.99,
    "category": "Updated Category",
    "brand": "Updated Brand",
    "stock": 90,
    "rating": 4.7    
}


def test_create_product_success(client: TestClient, db_session: Session, mock_qdrant_client: MagicMock):
    response = client.post("/products/", json=sample_product_data_create)
    assert response.status_code == 200 # Your endpoint returns 200 on successful POST
    data = response.json()
    assert data["name"] == sample_product_data_create["name"]
    assert data["product_id"] == sample_product_data_create["product_id"]
    assert "created_at" in data
    assert "updated_at" in data
    assert not data["is_deleted"]

    # Verify in DB
    db_product = db_session.query(ProductDB).filter(ProductDB.product_id == sample_product_data_create["product_id"]).first()
    assert db_product is not None
    assert db_product.name == sample_product_data_create["name"]

    # Verify Qdrant sync was called
    mock_qdrant_client.upsert.assert_called_once()
    args, kwargs = mock_qdrant_client.upsert.call_args
    assert kwargs['collection_name'] == VECTOR_DB_COLLECTION_PRODUCTS
    # Check if the point ID matches the expected deterministic UUID
    expected_qdrant_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, sample_product_data_create["product_id"]))
    assert any(p.id == expected_qdrant_id for p in kwargs['points'])


def test_create_product_duplicate_id(client: TestClient, db_session: Session):
    # Create the first product
    client.post("/products/", json=sample_product_data_create)

    # Attempt to create another product with the same product_id
    # Assuming your database has a unique constraint on product_id
    # and your API/DB layer handles this by raising an integrity error,
    # which FastAPI might turn into a 4xx error (e.g., 400 or 409 Conflict).
    # If not handled explicitly, it might be a 500. Let's assume 400 for now.
    # This depends on how your create_product endpoint handles DB integrity errors.
    # For this test to be meaningful, your ProductDB model should have unique=True for product_id
    # and your create_product endpoint should catch sqlalchemy.exc.IntegrityError.
    # If it doesn't, this test might expect a 500 or pass if no constraint.
    # Let's assume the DB has a unique constraint and the app returns 400 or 409.
    # For now, we'll check if the second POST fails.
    # A more robust test would mock the DB session to raise IntegrityError.
    
    # Check if product_id is unique in ProductDB model. If not, this test is less relevant.
    # Assuming ProductDB.product_id is unique.
    response = client.post("/products/", json=sample_product_data_create)
    assert response.status_code == 400 # Or 409, or 500 if not handled
    # Add more specific error message checking if your API provides one
    # e.g., assert "already exists" in response.json()["detail"].lower()


def test_create_product_invalid_data(client: TestClient):
    invalid_data = {"name": "Only Name"} # Missing required fields like product_id, price etc.
    response = client.post("/products/", json=invalid_data)
    assert response.status_code == 422 # Unprocessable Entity for Pydantic validation errors


def test_create_product_invalid_field_types(client: TestClient):
    test_cases = [
        ({**sample_product_data_create, "price": "not-a-float"}, "price"),
        ({**sample_product_data_create, "stock": "not-an-int"}, "stock"),
        ({**sample_product_data_create, "rating": "not-a-float"}, "rating"),
    ]
    for invalid_data, field_name in test_cases:
        response = client.post("/products/", json=invalid_data)
        assert response.status_code == 422
        assert any(err["loc"][-1] == field_name for err in response.json()["detail"])

def test_read_product_success(client: TestClient, db_session: Session):
    # First, create a product to read
    client.post("/products/", json=sample_product_data_create)

    response = client.get(f"/products/{sample_product_data_create['product_id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == sample_product_data_create["name"]
    assert data["product_id"] == sample_product_data_create["product_id"]

def test_read_product_not_found(client: TestClient):
    response = client.get("/products/NONEXISTENTID")
    assert response.status_code == 404


def test_read_soft_deleted_product_returns_404(client: TestClient, db_session: Session):
    # Create and then delete a product
    create_response = client.post("/products/", json=sample_product_data_create)
    assert create_response.status_code == 200
    delete_response = client.delete(f"/products/{sample_product_data_create['product_id']}")
    assert delete_response.status_code == 200

    # Attempt to read the soft-deleted product
    response = client.get(f"/products/{sample_product_data_create['product_id']}")
    assert response.status_code == 404

def test_read_products_success(client: TestClient, db_session: Session):
    # Create a couple of products
    client.post("/products/", json=sample_product_data_create)
    product2_data = {**sample_product_data_create, "product_id": "TESTPROD002", "name": "Test Product 2"}
    client.post("/products/", json=product2_data)

    response = client.get("/products/")
    assert response.status_code == 200
    data = response.json()
    # The number of products can vary if tests run in parallel or if db isn't perfectly clean,
    # but with function-scoped fixtures and rollback, it should be predictable.
    # We expect at least the two we created in this test.
    assert len(data) >= 2
    product_ids_in_response = [p["product_id"] for p in data]
    assert sample_product_data_create["product_id"] in product_ids_in_response
    assert product2_data["product_id"] in product_ids_in_response


def test_read_products_empty(client: TestClient, db_session: Session):
    # Ensure no products are present (db_session fixture handles rollback)
    response = client.get("/products/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0


def test_read_products_pagination(client: TestClient, db_session: Session):
    # Create 3 products
    products_to_create = [
        {**sample_product_data_create, "product_id": f"P{i:03}", "name": f"Product {i}"} for i in range(1, 4)
    ]
    for p_data in products_to_create:
        client.post("/products/", json=p_data)

    # Test skip and limit
    response = client.get("/products/?skip=1&limit=1")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["product_id"] == "P002" # Second product

def test_update_product_success(client: TestClient, db_session: Session, mock_qdrant_client: MagicMock):
    # Create a product first
    initial_response = client.post("/products/", json=sample_product_data_create)
    assert initial_response.status_code == 200
    mock_qdrant_client.reset_mock() # Reset mock for the update call
    update_payload = updated_product_data_create.copy()


    response = client.put(f"/products/{sample_product_data_create['product_id']}", json=update_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == updated_product_data_create["name"]
    assert data["price"] == updated_product_data_create["price"]
    assert data["product_id"] == sample_product_data_create["product_id"] # product_id should not change

    # Verify in DB
    db_product = db_session.query(ProductDB).filter(ProductDB.product_id == sample_product_data_create["product_id"]).first()
    assert db_product is not None
    assert db_product.name == updated_product_data_create["name"]

    # Verify Qdrant sync was called for update
    mock_qdrant_client.upsert.assert_called_once()
    args, kwargs = mock_qdrant_client.upsert.call_args
    assert kwargs['collection_name'] == VECTOR_DB_COLLECTION_PRODUCTS
    expected_qdrant_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, sample_product_data_create["product_id"]))
    assert any(p.id == expected_qdrant_id for p in kwargs['points'])


def test_update_product_not_found(client: TestClient):
    update_payload = updated_product_data_create.copy()
    response = client.put("/products/NONEXISTENTID", json=update_payload)
    assert response.status_code == 404


def test_update_product_invalid_field_types(client: TestClient):
    # Create a product first to have an ID to update
    client.post("/products/", json=sample_product_data_create)

    test_cases = [
        ({**updated_product_data_create, "price": "not-a-float"}, "price"),
        ({**updated_product_data_create, "stock": "not-an-int"}, "stock"),
    ]
    for invalid_data, field_name in test_cases:
        response = client.put(f"/products/{sample_product_data_create['product_id']}", json=invalid_data)
        assert response.status_code == 422
        assert any(err["loc"][-1] == field_name for err in response.json()["detail"])

def test_delete_product_success(client: TestClient, db_session: Session, mock_qdrant_client: MagicMock):
    # Create a product first
    initial_response = client.post("/products/", json=sample_product_data_create)
    assert initial_response.status_code == 200
    mock_qdrant_client.reset_mock() # Reset mock for the delete call

    response = client.delete(f"/products/{sample_product_data_create['product_id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["is_deleted"] is True
    assert data["product_id"] == sample_product_data_create["product_id"]

    # Verify in DB (soft delete)
    db_product = db_session.query(ProductDB).filter(ProductDB.product_id == sample_product_data_create["product_id"]).first()
    assert db_product is not None
    assert db_product.is_deleted is True

    # Verify Qdrant delete was called
    mock_qdrant_client.delete.assert_called_once()
    args, kwargs = mock_qdrant_client.delete.call_args
    assert kwargs['collection_name'] == VECTOR_DB_COLLECTION_PRODUCTS
    expected_qdrant_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, sample_product_data_create["product_id"]))
    assert kwargs['points_selector'].points[0] == expected_qdrant_id # Assuming PointIdsList

def test_delete_product_not_found(client: TestClient):
    response = client.delete("/products/NONEXISTENTID")
    assert response.status_code == 404


def test_delete_already_deleted_product(client: TestClient, db_session: Session):
    # Create and delete a product
    client.post("/products/", json=sample_product_data_create)
    client.delete(f"/products/{sample_product_data_create['product_id']}")

    # Attempt to delete it again
    response = client.delete(f"/products/{sample_product_data_create['product_id']}")
    # The behavior here depends on your API logic.
    # Usually, it would return 404 as the "active" product is not found.
    assert response.status_code == 404