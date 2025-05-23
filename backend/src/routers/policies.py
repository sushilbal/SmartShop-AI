from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
import logging

from src.models import StorePolicy, StorePolicyCreate, StorePolicyDB
from src.embedding_sync import update_policy_in_qdrant, delete_policy_from_qdrant
from src.dependencies import get_db, get_qdrant_db_client 

router = APIRouter(
    prefix="/policies",
    tags=["policies"],
)

logger = logging.getLogger(__name__)

@router.get("/", response_model=List[StorePolicy])
def read_policies(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    policies = db.query(StorePolicyDB).filter(StorePolicyDB.is_deleted == False).offset(skip).limit(limit).all()
    return policies

@router.get("/{policy_id}", response_model=StorePolicy)
def read_policy(policy_id: int, db: Session = Depends(get_db)):
    policy = db.query(StorePolicyDB).filter(StorePolicyDB.policy_id == policy_id, StorePolicyDB.is_deleted == False).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy

@router.post("/", response_model=StorePolicy)
def create_policy(
    policy: StorePolicyCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    q_client = Depends(get_qdrant_db_client)
):
    db_policy = StorePolicyDB(**policy.model_dump())
    db.add(db_policy)
    db.commit()
    db.refresh(db_policy)
    if q_client:
        background_tasks.add_task(update_policy_in_qdrant, q_client, db_policy.policy_id, policy.model_dump())
    return db_policy

@router.put("/{policy_id}", response_model=StorePolicy)
def update_policy(
    policy_id: int,
    policy: StorePolicyCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    q_client = Depends(get_qdrant_db_client)
):
    db_policy = db.query(StorePolicyDB).filter(StorePolicyDB.policy_id == policy_id, StorePolicyDB.is_deleted == False).first()
    if not db_policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    for key, value in policy.model_dump(exclude_unset=True).items():
        setattr(db_policy, key, value)
    db.commit()
    db.refresh(db_policy)
    if q_client:
        background_tasks.add_task(update_policy_in_qdrant, q_client, policy_id, policy.model_dump())
    return db_policy

@router.delete("/{policy_id}", response_model=StorePolicy)
def delete_policy(
    policy_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    q_client = Depends(get_qdrant_db_client)
):
    db_policy = db.query(StorePolicyDB).filter(StorePolicyDB.policy_id == policy_id, StorePolicyDB.is_deleted == False).first()
    if not db_policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    db_policy.is_deleted = True
    db.commit()
    db.refresh(db_policy)
    if q_client:
        background_tasks.add_task(delete_policy_from_qdrant, q_client, policy_id)
    return db_policy