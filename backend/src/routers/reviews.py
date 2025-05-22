from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from src.models import Review, ReviewCreate, ReviewDB, ProductDB
from src.embedding_sync import update_review_in_qdrant, delete_review_from_qdrant
from src.dependencies import get_db, get_qdrant_db_client 

router = APIRouter(
    prefix="/reviews",
    tags=["reviews"],
)

logger = logging.getLogger(__name__)

@router.get("/", response_model=List[Review])
def read_reviews(skip: int = 0, limit: int = 100, product_id: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(ReviewDB).filter(ReviewDB.is_deleted == False)
    if product_id:
        query = query.filter(ReviewDB.product_id == product_id)
    reviews = query.offset(skip).limit(limit).all()
    return reviews

@router.get("/{review_id}", response_model=Review)
def read_review(review_id: int, db: Session = Depends(get_db)):
    review = db.query(ReviewDB).filter(ReviewDB.review_id == review_id, ReviewDB.is_deleted == False).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review

@router.post("/", response_model=Review)
def create_review(review: ReviewCreate, db: Session = Depends(get_db), q_client = Depends(get_qdrant_db_client)):
    product = db.query(ProductDB).filter(ProductDB.product_id == review.product_id, ProductDB.is_deleted == False).first()
    if not product:
        raise HTTPException(status_code=400, detail="Product not found")

    db_review = ReviewDB(**review.model_dump())
    db.add(db_review)
    db.commit()
    db.refresh(db_review)
    if q_client:
        try:
            update_review_in_qdrant(q_client, db_review.review_id, review.model_dump())
        except Exception as e:
            logger.error(f"Failed to sync new review {db_review.review_id} to Qdrant: {e}", exc_info=True)
    return db_review

@router.put("/{review_id}", response_model=Review)
def update_review(review_id: int, review: ReviewCreate, db: Session = Depends(get_db), q_client = Depends(get_qdrant_db_client)):
    db_review = db.query(ReviewDB).filter(ReviewDB.review_id == review_id, ReviewDB.is_deleted == False).first()
    if not db_review:
        raise HTTPException(status_code=404, detail="Review not found")
    if review.product_id != db_review.product_id:
        product = db.query(ProductDB).filter(ProductDB.product_id == review.product_id, ProductDB.is_deleted == False).first()
        if not product:
            raise HTTPException(status_code=400, detail="New product_id for review not found")
            
    for key, value in review.model_dump(exclude_unset=True).items():
        setattr(db_review, key, value)
    db.commit()
    db.refresh(db_review)
    if q_client:
        try:
            update_review_in_qdrant(q_client, review_id, review.model_dump())
        except Exception as e:
            logger.error(f"Failed to sync updated review {review_id} to Qdrant: {e}", exc_info=True)
    return db_review

@router.delete("/{review_id}", response_model=Review)
def delete_review(review_id: int, db: Session = Depends(get_db), q_client = Depends(get_qdrant_db_client)):
    db_review = db.query(ReviewDB).filter(ReviewDB.review_id == review_id, ReviewDB.is_deleted == False).first()
    if not db_review:
        raise HTTPException(status_code=404, detail="Review not found")
    db_review.is_deleted = True
    db.commit()
    db.refresh(db_review)
    if q_client:
        try:
            delete_review_from_qdrant(q_client, review_id)
        except Exception as e:
            logger.error(f"Failed to delete review {review_id} from Qdrant: {e}", exc_info=True)
    return db_review