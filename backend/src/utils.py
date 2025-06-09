from sqlalchemy.orm import Session
from fastapi import HTTPException
from typing import Type, TypeVar, Any
import logging

logger = logging.getLogger(__name__)

ModelType = TypeVar("ModelType")

def get_obj_or_404(db: Session, model: Type[ModelType], obj_id: Any, action: str = "find") -> ModelType:
    """
    Fetches an object by its primary key, filtering out soft-deleted records.
    Raises HTTPException 404 if not found.
    """
    pk_name = model.__mapper__.primary_key[0].name
    query = db.query(model).filter(getattr(model, pk_name) == obj_id)
    if hasattr(model, 'is_deleted'):
        query = query.filter(model.is_deleted == False)
    
    db_obj = query.first()
    if not db_obj:
        raise HTTPException(status_code=404, detail=f"{model.__name__} to {action} not found with ID {obj_id}")
    return db_obj