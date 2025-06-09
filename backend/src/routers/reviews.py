from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from src.models import Review, ReviewCreate, ReviewDB, ProductDB
from src.embedding_sync import update_review_in_qdrant, delete_review_from_qdrant
from src.dependencies import get_db, get_qdrant_db_client
from src.utils import get_obj_or_404

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
    return get_obj_or_404(db, ReviewDB, review_id, action="read")

@router.post("/", response_model=Review)
def create_review(
    review: ReviewCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    q_client = Depends(get_qdrant_db_client)
):
    # Validate product existence
    try:
        get_obj_or_404(db, ProductDB, review.product_id, action="assign to review")
    except HTTPException as e:
        if e.status_code == 404: # Product not found
            raise HTTPException(status_code=400, detail=f"Product with ID '{review.product_id}' not found to associate with the review.")
        raise # Re-raise other potential errors

    db_review = ReviewDB(**review.model_dump())
    db.add(db_review)
    db.commit()
    db.refresh(db_review)
    if q_client:
        background_tasks.add_task(update_review_in_qdrant, q_client, db_review.review_id, review.model_dump())
    return db_review

@router.put("/{review_id}", response_model=Review)
def update_review(
    review_id: int,
    review: ReviewCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    q_client = Depends(get_qdrant_db_client)
):
    db_review = get_obj_or_404(db, ReviewDB, review_id, action="update")

    if review.product_id != db_review.product_id:
        try:
            get_obj_or_404(db, ProductDB, review.product_id, action="assign to review")
        except HTTPException as e:
            if e.status_code == 404: # New product not found
                raise HTTPException(status_code=400, detail=f"New product_id '{review.product_id}' for review not found.")
            raise

    for key, value in review.model_dump(exclude_unset=True).items():
        setattr(db_review, key, value)
    db.commit()
    db.refresh(db_review)
    if q_client:
        background_tasks.add_task(update_review_in_qdrant, q_client, review_id, review.model_dump())
    return db_review

@router.delete("/{review_id}", response_model=Review)
def delete_review(
    review_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    q_client = Depends(get_qdrant_db_client)
):
    db_review = get_obj_or_404(db, ReviewDB, review_id, action="delete")
    db_review.is_deleted = True
    db.commit()
    db.refresh(db_review)
    if q_client:
        background_tasks.add_task(delete_review_from_qdrant, q_client, review_id)
    return db_review