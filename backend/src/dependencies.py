from sqlalchemy.orm import Session
import logging

from config.config import get_qdrant_client # For Qdrant client
from src.database import SessionLocal

logger = logging.getLogger(__name__)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_qdrant_db_client(): # Renamed to avoid conflict if FastAPI uses 'client'
    try:
        return get_qdrant_client() # This is from config.config
    except Exception as e:
        logger.error(f"Failed to get Qdrant client for API request: {e}")
        # Depending on strictness, you might raise HTTPException here
        return None