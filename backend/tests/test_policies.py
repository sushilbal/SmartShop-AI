from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import MagicMock, ANY

from src.models import StorePolicyDB # Import your DB model
from config.config import VECTOR_DB_COLLECTION_POLICIES # Import collection name

sample_policy_data_create = {
    "policy_type": "Shipping",
    "description": "Standard shipping takes 3-5 business days.",
    "conditions": "Applies to domestic orders only.",
    "timeframe": "3-5 business days"
}

updated_policy_data_create = {
    "policy_type": "Returns",
    "description": "Returns accepted within 30 days of purchase.",
    "conditions": "Item must be unused and in original packaging.",
    "timeframe": "30 days"
}

def test_create_policy_success(client: TestClient, db_session: Session, mock_qdrant_client: MagicMock):
    response = client.post("/policies/", json=sample_policy_data_create)
    if response.status_code != 200:
        print("\nDEBUG: test_create_policy_success FAILED. Response JSON:")
        try:
            print(response.json())
        except Exception as e_json:
            print(f"Could not parse response as JSON: {e_json}")
            print(f"Response text: {response.text}")
    assert response.status_code == 200
    data = response.json()
    assert data["policy_type"] == sample_policy_data_create["policy_type"]
    assert data["description"] == sample_policy_data_create["description"]
    assert "policy_id" in data
    created_policy_id = data["policy_id"]

    # Verify in DB
    db_policy = db_session.query(StorePolicyDB).filter(StorePolicyDB.policy_id == created_policy_id).first()
    assert db_policy is not None
    assert db_policy.description == sample_policy_data_create["description"]

    # Verify Qdrant sync was called (for chunks)
    mock_qdrant_client.upsert.assert_called_once()
    args, kwargs = mock_qdrant_client.upsert.call_args
    assert kwargs['collection_name'] == VECTOR_DB_COLLECTION_POLICIES
    assert len(kwargs['points']) > 0 # Should have at least one chunk
    assert kwargs['points'][0].payload["original_policy_id"] == created_policy_id

def test_create_policy_invalid_data(client: TestClient):
    invalid_data = {"description": "Only description"} # Missing policy_type
    response = client.post("/policies/", json=invalid_data)
    assert response.status_code == 422

def test_read_policy_success(client: TestClient, db_session: Session):
    create_response = client.post("/policies/", json=sample_policy_data_create)
    created_policy_id = create_response.json()["policy_id"]

    response = client.get(f"/policies/{created_policy_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["policy_id"] == created_policy_id
    assert data["description"] == sample_policy_data_create["description"]

def test_read_policy_not_found(client: TestClient):
    response = client.get("/policies/999999") # Non-existent ID
    assert response.status_code == 404

def test_read_policies_all(client: TestClient, db_session: Session):
    client.post("/policies/", json={**sample_policy_data_create, "policy_type": "Type A"})
    client.post("/policies/", json={**sample_policy_data_create, "policy_type": "Type B"})

    response = client.get("/policies/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2

def test_update_policy_success(client: TestClient, db_session: Session, mock_qdrant_client: MagicMock):
    create_response = client.post("/policies/", json=sample_policy_data_create)
    created_policy_id = create_response.json()["policy_id"]
    mock_qdrant_client.reset_mock()

    response = client.put(f"/policies/{created_policy_id}", json=updated_policy_data_create)
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == updated_policy_data_create["description"]
    assert data["policy_type"] == updated_policy_data_create["policy_type"]

    # Verify in DB
    db_policy = db_session.query(StorePolicyDB).filter(StorePolicyDB.policy_id == created_policy_id).first()
    assert db_policy.description == updated_policy_data_create["description"]

    # Verify Qdrant sync was called
    mock_qdrant_client.upsert.assert_called_once()
    args, kwargs = mock_qdrant_client.upsert.call_args
    assert kwargs['collection_name'] == VECTOR_DB_COLLECTION_POLICIES
    assert kwargs['points'][0].payload["original_policy_id"] == created_policy_id

def test_update_policy_not_found(client: TestClient):
    response = client.put("/policies/999999", json=updated_policy_data_create)
    assert response.status_code == 404

def test_delete_policy_success(client: TestClient, db_session: Session, mock_qdrant_client: MagicMock):
    create_response = client.post("/policies/", json=sample_policy_data_create)
    created_policy_id = create_response.json()["policy_id"]
    mock_qdrant_client.reset_mock()

    response = client.delete(f"/policies/{created_policy_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["is_deleted"] is True

    # Verify in DB (soft delete)
    db_policy = db_session.query(StorePolicyDB).filter(StorePolicyDB.policy_id == created_policy_id).first()
    assert db_policy.is_deleted is True

    # Verify Qdrant delete was called with a filter
    mock_qdrant_client.delete.assert_called_once()
    args, kwargs = mock_qdrant_client.delete.call_args
    assert kwargs['collection_name'] == VECTOR_DB_COLLECTION_POLICIES
    assert kwargs['points_selector'].filter.must[0].key == "original_policy_id"
    assert kwargs['points_selector'].filter.must[0].match.value == created_policy_id

def test_delete_policy_not_found(client: TestClient):
    response = client.delete("/policies/999999")
    assert response.status_code == 404

def test_delete_already_deleted_policy(client: TestClient, db_session: Session):
    create_response = client.post("/policies/", json=sample_policy_data_create)
    created_policy_id = create_response.json()["policy_id"]
    client.delete(f"/policies/{created_policy_id}") # First delete

    response = client.delete(f"/policies/{created_policy_id}") # Second delete
    assert response.status_code == 404