from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import MagicMock, ANY, call

from src.models import ProductDB, ReviewDB # Import your DB models
from config.config import VECTOR_DB_COLLECTION_REVIEWS # Import collection name

# Sample data for a product, as reviews depend on products
sample_product_data_for_review_tests = {
    "product_id": "REVIEWPROD001",
    "name": "Product for Reviews",
    "description": "A product to test reviews against.",
    "price": 10.00,
    "category": "Review Test Category",
    "brand": "Review Test Brand",
    "stock": 10,
    "rating": 3.0
}

sample_review_data_create = {
    "product_id": "REVIEWPROD001",
    "user_id": "testuser123",
    "rating": 5,
    "text": "This product is amazing! Highly recommend.",
    # review_date is usually set by the server or DB default
}

updated_review_data_create = {
    "product_id": "REVIEWPROD001", # Assuming product_id might not change, or test separately
    "user_id": "testuser123_updated",
    "rating": 4,
    "text": "Still good, but found a small issue."
}

def create_test_product(client: TestClient):
    """Helper to create a product for review tests."""
    response = client.post("/products/", json=sample_product_data_for_review_tests)
    assert response.status_code == 200, "Failed to create prerequisite product for review tests"
    return response.json()["product_id"]

def test_create_review_success(client: TestClient, db_session: Session, mock_qdrant_client: MagicMock):
    product_id = create_test_product(client)
    # Reset the mock after product creation, so we only count calls for review sync
    mock_qdrant_client.reset_mock()

    review_payload = {**sample_review_data_create, "product_id": product_id}

    response = client.post("/reviews/", json=review_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["product_id"] == product_id
    assert data["text"] == sample_review_data_create["text"]
    assert "review_id" in data
    created_review_id = data["review_id"]

    # Verify in DB
    db_review = db_session.query(ReviewDB).filter(ReviewDB.review_id == created_review_id).first()
    assert db_review is not None
    assert db_review.text == sample_review_data_create["text"]

    # Verify Qdrant sync was called (for chunks)
    mock_qdrant_client.upsert.assert_called_once()
    args, kwargs = mock_qdrant_client.upsert.call_args
    assert kwargs['collection_name'] == VECTOR_DB_COLLECTION_REVIEWS
    assert len(kwargs['points']) > 0 # Should have at least one chunk
    assert kwargs['points'][0].payload["original_review_id"] == created_review_id

def test_create_review_for_nonexistent_product(client: TestClient):
    review_payload = {**sample_review_data_create, "product_id": "NONEXISTENTPROD"}
    response = client.post("/reviews/", json=review_payload)
    assert response.status_code == 400 # As per your API logic
    assert "product not found" in response.json()["detail"].lower()

def test_create_review_invalid_data(client: TestClient):
    product_id = create_test_product(client)
    invalid_data = {"product_id": product_id, "rating": "not-an-int"} # Missing text, invalid rating
    response = client.post("/reviews/", json=invalid_data)
    assert response.status_code == 422

def test_read_review_success(client: TestClient, db_session: Session):
    product_id = create_test_product(client)
    review_payload = {**sample_review_data_create, "product_id": product_id}
    create_response = client.post("/reviews/", json=review_payload)
    created_review_id = create_response.json()["review_id"]

    response = client.get(f"/reviews/{created_review_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["review_id"] == created_review_id
    assert data["text"] == sample_review_data_create["text"]

def test_read_review_not_found(client: TestClient):
    response = client.get("/reviews/999999") # Non-existent ID
    assert response.status_code == 404

def test_read_reviews_all(client: TestClient, db_session: Session):
    product_id = create_test_product(client)
    client.post("/reviews/", json={**sample_review_data_create, "product_id": product_id, "text": "Review 1"})
    client.post("/reviews/", json={**sample_review_data_create, "product_id": product_id, "text": "Review 2"})

    response = client.get("/reviews/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2

def test_read_reviews_for_product(client: TestClient, db_session: Session):
    product_id1 = create_test_product(client) # Creates REVIEWPROD001
    product_id2 = client.post("/products/", json={**sample_product_data_for_review_tests, "product_id": "REVIEWPROD002"}).json()["product_id"]

    client.post("/reviews/", json={**sample_review_data_create, "product_id": product_id1, "text": "Review for P1"})
    client.post("/reviews/", json={**sample_review_data_create, "product_id": product_id2, "text": "Review for P2"})

    response = client.get(f"/reviews/?product_id={product_id1}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["text"] == "Review for P1"
    assert data[0]["product_id"] == product_id1

def test_update_review_success(client: TestClient, db_session: Session, mock_qdrant_client: MagicMock):
    product_id = create_test_product(client)
    review_payload = {**sample_review_data_create, "product_id": product_id}
    create_response = client.post("/reviews/", json=review_payload)
    created_review_id = create_response.json()["review_id"]
    mock_qdrant_client.reset_mock()

    update_payload = {**updated_review_data_create, "product_id": product_id}
    response = client.put(f"/reviews/{created_review_id}", json=update_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["text"] == updated_review_data_create["text"]
    assert data["rating"] == updated_review_data_create["rating"]

    # Verify in DB
    db_review = db_session.query(ReviewDB).filter(ReviewDB.review_id == created_review_id).first()
    assert db_review.text == updated_review_data_create["text"]

    # Verify Qdrant sync was called
    mock_qdrant_client.upsert.assert_called_once()
    args, kwargs = mock_qdrant_client.upsert.call_args
    assert kwargs['collection_name'] == VECTOR_DB_COLLECTION_REVIEWS
    assert kwargs['points'][0].payload["original_review_id"] == created_review_id

def test_update_review_not_found(client: TestClient):
    response = client.put("/reviews/999999", json=updated_review_data_create)
    assert response.status_code == 404

def test_update_review_to_nonexistent_product(client: TestClient):
    product_id = create_test_product(client)
    review_payload = {**sample_review_data_create, "product_id": product_id}
    create_response = client.post("/reviews/", json=review_payload)
    created_review_id = create_response.json()["review_id"]

    update_payload = {**updated_review_data_create, "product_id": "NONEXISTENTPRODFORREVIEW"}
    response = client.put(f"/reviews/{created_review_id}", json=update_payload)
    assert response.status_code == 400
    assert "new product_id for review not found" in response.json()["detail"].lower()

def test_delete_review_success(client: TestClient, db_session: Session, mock_qdrant_client: MagicMock):
    product_id = create_test_product(client)
    review_payload = {**sample_review_data_create, "product_id": product_id}
    create_response = client.post("/reviews/", json=review_payload)
    created_review_id = create_response.json()["review_id"]
    mock_qdrant_client.reset_mock()

    response = client.delete(f"/reviews/{created_review_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["is_deleted"] is True

    # Verify in DB (soft delete)
    db_review = db_session.query(ReviewDB).filter(ReviewDB.review_id == created_review_id).first()
    assert db_review.is_deleted is True

    # Verify Qdrant delete was called with a filter
    mock_qdrant_client.delete.assert_called_once()
    args, kwargs = mock_qdrant_client.delete.call_args
    assert kwargs['collection_name'] == VECTOR_DB_COLLECTION_REVIEWS
    assert kwargs['points_selector'].filter.must[0].key == "original_review_id"
    assert kwargs['points_selector'].filter.must[0].match.value == created_review_id

def test_delete_review_not_found(client: TestClient):
    response = client.delete("/reviews/999999")
    assert response.status_code == 404

def test_delete_already_deleted_review(client: TestClient, db_session: Session):
    product_id = create_test_product(client)
    review_payload = {**sample_review_data_create, "product_id": product_id}
    create_response = client.post("/reviews/", json=review_payload)
    created_review_id = create_response.json()["review_id"]
    client.delete(f"/reviews/{created_review_id}") # First delete

    response = client.delete(f"/reviews/{created_review_id}") # Second delete
    assert response.status_code == 404