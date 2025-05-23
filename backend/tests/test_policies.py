from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import MagicMock, ANY

from src.models import StorePolicyDB # Import your DB model
from config.config import VECTOR_DB_COLLECTION_POLICIES # Import collection name

# Helper to construct content string consistently
def _construct_content(description: str, conditions: str, timeframe: str) -> str:
    return f"{description}\nConditions: {conditions}\nTimeframe: {timeframe}".strip()

_sample_description = "Standard shipping takes 3-5 business days."
_sample_conditions = "Applies to domestic orders only."
_sample_timeframe = "3-5 business days"
sample_policy_data_create = {
    "policy_type": "Shipping",
    "description": _sample_description,
    "conditions": _sample_conditions,
    "timeframe": _sample_timeframe,
    "content": _construct_content(_sample_description, _sample_conditions, _sample_timeframe)
}

_updated_description = "Returns accepted within 30 days of purchase."
_updated_conditions = "Item must be unused and in original packaging."
_updated_timeframe = "30 days"
updated_policy_data_create = {
    "policy_type": "Returns",
    "description": _updated_description,
    "conditions": _updated_conditions,
    "timeframe": _updated_timeframe,
    "content": _construct_content(_updated_description, _updated_conditions, _updated_timeframe)
}

def test_create_policy_success(client: TestClient, db_session: Session, mock_qdrant_client: MagicMock):
    response = client.post("/policies/", json=sample_policy_data_create)
    assert response.status_code == 200
    data = response.json()
    assert data["policy_type"] == sample_policy_data_create["policy_type"]
    assert data["description"] == sample_policy_data_create["description"]
    assert "policy_id" in data
    created_policy_id = data["policy_id"]
    assert data["content"] == sample_policy_data_create["content"]

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


def test_create_policy_invalid_data_missing_required_fields(client: TestClient):
    # Create a valid payload missing one required field at a time
    valid_payload_base = {
        "policy_type": "Test",
        "description": "Test desc",
        "content": "Test content"
    }

    # Missing policy_type
    payload_missing_type = valid_payload_base.copy()
    del payload_missing_type["policy_type"]
    response_missing_type = client.post("/policies/", json=payload_missing_type)
    assert response_missing_type.status_code == 422

    # Missing description
    payload_missing_desc = valid_payload_base.copy()
    del payload_missing_desc["description"]
    response_missing_desc = client.post("/policies/", json=payload_missing_desc)
    assert response_missing_desc.status_code == 422

    # Missing content (if content is indeed required by StorePolicyCreate)
    payload_missing_content = valid_payload_base.copy()
    del payload_missing_content["content"]
    response_missing_content = client.post("/policies/", json=payload_missing_content)
    assert response_missing_content.status_code == 422

def test_create_policy_invalid_data_wrong_type(client: TestClient):
    # policy_type as integer instead of string
    invalid_payload = {
        "policy_type": 123,
        "description": "Wrong type for policy_type",
        "content": "Content with wrong type for policy_type"
    }
    response = client.post("/policies/", json=invalid_payload)
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
    # Clear existing policies for a clean test or ensure DB is clean via fixture
    # For simplicity, we assume a relatively clean state or that other tests don't interfere too much.
    # Create a known number of policies
    policy_a_data = {**sample_policy_data_create, "policy_type": "Type A Test Read All"}
    policy_b_data = {**sample_policy_data_create, "policy_type": "Type B Test Read All"}
    
    client.post("/policies/", json=policy_a_data)
    client.post("/policies/", json=policy_b_data)

    response = client.get("/policies/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2
    # Check if the created policies are in the list
    policy_types_in_response = [p.get("policy_type") for p in data]
    assert policy_a_data["policy_type"] in policy_types_in_response
    assert policy_b_data["policy_type"] in policy_types_in_response

def test_read_policies_pagination(client: TestClient, db_session: Session):
    # Create 3 policies
    base_desc = "Pagination test policy"
    policy1_data = {**sample_policy_data_create, "policy_type": "PagePolicy 1", "description": f"{base_desc} 1"}
    policy2_data = {**sample_policy_data_create, "policy_type": "PagePolicy 2", "description": f"{base_desc} 2"}
    policy3_data = {**sample_policy_data_create, "policy_type": "PagePolicy 3", "description": f"{base_desc} 3"}

    client.post("/policies/", json=policy1_data)
    client.post("/policies/", json=policy2_data)
    client.post("/policies/", json=policy3_data)

    # Test limit
    response_limit_1 = client.get("/policies/?limit=1")
    assert response_limit_1.status_code == 200
    assert len(response_limit_1.json()) <= 1 # Could be 1 if other tests didn't add more, or more if they did.
                                           # For exact count, ensure clean DB state.

    # Test skip and limit
    # Assuming policies are ordered by insertion or ID for predictability.
    # This part might need adjustment based on default ordering or specific ordering in the endpoint.
    # For robust pagination tests, it's often better to fetch all, then slice and compare.
    all_policies_response = client.get("/policies/?limit=100") # Get a large number
    all_policies = all_policies_response.json()
    
    response_skip1_limit1 = client.get("/policies/?skip=1&limit=1")
    assert response_skip1_limit1.status_code == 200
    if len(all_policies) > 1 and len(response_skip1_limit1.json()) == 1:
        assert response_skip1_limit1.json()[0]["policy_id"] == all_policies[1]["policy_id"]

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

def test_update_policy_partial(client: TestClient, db_session: Session, mock_qdrant_client: MagicMock):
    initial_data = {**sample_policy_data_create, "policy_type": "PartialUpdateTest"}
    create_response = client.post("/policies/", json=initial_data)
    assert create_response.status_code == 200
    created_policy_id = create_response.json()["policy_id"]
    original_conditions = create_response.json()["conditions"] # Assuming 'conditions' is part of the response model
    mock_qdrant_client.reset_mock()

    partial_update_data = {"description": "Partially updated description"}
    response = client.put(f"/policies/{created_policy_id}", json=partial_update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == partial_update_data["description"]
    assert data["policy_type"] == initial_data["policy_type"] # Should not change
    assert data["conditions"] == original_conditions # Should not change if not in payload and exclude_unset=True

    # Verify in DB
    db_policy = db_session.query(StorePolicyDB).filter(StorePolicyDB.policy_id == created_policy_id).first()
    assert db_policy.description == partial_update_data["description"]
    assert db_policy.policy_type == initial_data["policy_type"]

    # Verify Qdrant sync
    mock_qdrant_client.upsert.assert_called_once()

def test_update_policy_not_found(client: TestClient):
    response = client.put("/policies/999999", json=updated_policy_data_create)
    assert response.status_code == 404

def test_update_soft_deleted_policy(client: TestClient, db_session: Session):
    create_response = client.post("/policies/", json=sample_policy_data_create)
    created_policy_id = create_response.json()["policy_id"]
    client.delete(f"/policies/{created_policy_id}") # Soft delete

    response = client.put(f"/policies/{created_policy_id}", json=updated_policy_data_create)
    assert response.status_code == 404 # Should not be able to update a soft-deleted policy

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
