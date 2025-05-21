from fastapi import FastAPI, HTTPException, Depends, Query
from typing import List, Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import Session
from config.config import DATABASE_URL, get_qdrant_client
from src.models import Product, ProductCreate, ProductDB, Review, ReviewCreate, ReviewDB, StorePolicy, StorePolicyCreate, StorePolicyDB, Base  # Import from models.py
from datetime import datetime
import logging # For logging Qdrant sync errors

# Import Qdrant sync functions
from src.embedding_sync import (
    update_product_in_qdrant, delete_product_from_qdrant,
    update_review_in_qdrant, delete_review_from_qdrant,
    update_policy_in_qdrant, delete_policy_from_qdrant
)
from sqlalchemy.exc import IntegrityError

# --- SQLAlchemy Setup ---
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- FastAPI App ---
app = FastAPI()
logger = logging.getLogger(__name__)

# --- Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_qdrant_db_client(): # Renamed to avoid conflict if FastAPI uses 'client'
    try:
        return get_qdrant_client()
    except Exception as e:
        logger.error(f"Failed to get Qdrant client for API request: {e}")
        # Depending on strictness, you might raise HTTPException here
        return None
# --- API Endpoints ---

# --- Product Endpoints ---
@app.get("/products/", response_model=List[Product])
def read_products(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    products = db.query(ProductDB).filter(ProductDB.is_deleted == False).offset(skip).limit(limit).all()
    return products

@app.get("/products/{product_id}", response_model=Product)
def read_product(product_id: str, db: Session = Depends(get_db)):
    product = db.query(ProductDB).filter(ProductDB.product_id == product_id, ProductDB.is_deleted == False).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@app.post("/products/", response_model=Product)
def create_product(product: ProductCreate, db: Session = Depends(get_db), q_client = Depends(get_qdrant_db_client)):
    try:
        db_product = ProductDB(**product.model_dump())
        db.add(db_product)
        db.commit()
        db.refresh(db_product)
    except IntegrityError: # Catch duplicate key errors or other unique constraint violations
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Product with ID '{product.product_id}' already exists or violates a unique constraint.")
    # Sync with Qdrant (ensure product_id is correctly passed if it's part of product_data)
    if q_client:
        try:
            update_product_in_qdrant(q_client, db_product.product_id, product.model_dump())
        except Exception as e:
            logger.error(f"Failed to sync new product {db_product.product_id} to Qdrant: {e}", exc_info=True)
    # Else: Qdrant client not available, logged in get_qdrant_db_client
    return db_product

@app.put("/products/{product_id}", response_model=Product)
def update_product(product_id: str, product: ProductCreate, db: Session = Depends(get_db), q_client = Depends(get_qdrant_db_client)):
    db_product = db.query(ProductDB).filter(ProductDB.product_id == product_id, ProductDB.is_deleted == False).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    for key, value in product.model_dump(exclude_unset=True).items(): # exclude_unset for partial updates
        setattr(db_product, key, value)
    db.commit()
    db.refresh(db_product)
    # Sync with Qdrant
    if q_client:
        try:
            update_product_in_qdrant(q_client, product_id, product.model_dump())
        except Exception as e:
            logger.error(f"Failed to sync updated product {product_id} to Qdrant: {e}", exc_info=True)
    return db_product

@app.delete("/products/{product_id}", response_model=Product)
def delete_product(product_id: str, db: Session = Depends(get_db), q_client = Depends(get_qdrant_db_client)):
    db_product = db.query(ProductDB).filter(ProductDB.product_id == product_id, ProductDB.is_deleted == False).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    db_product.is_deleted = True #soft delete
    db.commit()
    db.refresh(db_product)
    # Sync with Qdrant (delete)
    if q_client:
        try:
            delete_product_from_qdrant(q_client, product_id)
        except Exception as e:
            logger.error(f"Failed to delete product {product_id} from Qdrant: {e}", exc_info=True)
    return db_product

# --- Review Endpoints ---
@app.get("/reviews/", response_model=List[Review])
def read_reviews(skip: int = 0, limit: int = 100, product_id: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(ReviewDB).filter(ReviewDB.is_deleted == False)
    if product_id:
        query = query.filter(ReviewDB.product_id == product_id)
    reviews = query.offset(skip).limit(limit).all()
    return reviews

@app.get("/reviews/{review_id}", response_model=Review)
def read_review(review_id: int, db: Session = Depends(get_db)):
    review = db.query(ReviewDB).filter(ReviewDB.review_id == review_id, ReviewDB.is_deleted == False).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review

@app.post("/reviews/", response_model=Review)
def create_review(review: ReviewCreate, db: Session = Depends(get_db), q_client = Depends(get_qdrant_db_client)):
    # Check if the product exists
    product = db.query(ProductDB).filter(ProductDB.product_id == review.product_id, ProductDB.is_deleted == False).first()
    if not product:
        raise HTTPException(status_code=400, detail="Product not found")

    db_review = ReviewDB(**review.model_dump())
    db.add(db_review)
    db.commit()
    db.refresh(db_review)
    # Sync with Qdrant
    if q_client:
        try:
            update_review_in_qdrant(q_client, db_review.review_id, review.model_dump())
        except Exception as e:
            logger.error(f"Failed to sync new review {db_review.review_id} to Qdrant: {e}", exc_info=True)
    return db_review

@app.put("/reviews/{review_id}", response_model=Review)
def update_review(review_id: int, review: ReviewCreate, db: Session = Depends(get_db), q_client = Depends(get_qdrant_db_client)):
    db_review = db.query(ReviewDB).filter(ReviewDB.review_id == review_id, ReviewDB.is_deleted == False).first()
    if not db_review:
        raise HTTPException(status_code=404, detail="Review not found")
    # Check if the product exists if product_id is being updated
    if review.product_id != db_review.product_id:
        product = db.query(ProductDB).filter(ProductDB.product_id == review.product_id, ProductDB.is_deleted == False).first()
        if not product:
            raise HTTPException(status_code=400, detail="New product_id for review not found")
            
    for key, value in review.model_dump(exclude_unset=True).items(): # exclude_unset for partial updates
        setattr(db_review, key, value)
    db.commit()
    db.refresh(db_review)
    # Sync with Qdrant
    if q_client:
        try:
            update_review_in_qdrant(q_client, review_id, review.model_dump())
        except Exception as e:
            logger.error(f"Failed to sync updated review {review_id} to Qdrant: {e}", exc_info=True)
    return db_review

@app.delete("/reviews/{review_id}", response_model=Review)
def delete_review(review_id: int, db: Session = Depends(get_db), q_client = Depends(get_qdrant_db_client)):
    db_review = db.query(ReviewDB).filter(ReviewDB.review_id == review_id, ReviewDB.is_deleted == False).first()
    if not db_review:
        raise HTTPException(status_code=404, detail="Review not found")
    db_review.is_deleted = True #soft delete
    db.commit()
    db.refresh(db_review)
    # Sync with Qdrant (delete)
    if q_client:
        try:
            delete_review_from_qdrant(q_client, review_id)
        except Exception as e:
            logger.error(f"Failed to delete review {review_id} from Qdrant: {e}", exc_info=True)
    return db_review

# --- Store Policy Endpoints ---
@app.get("/policies/", response_model=List[StorePolicy])
def read_policies(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    policies = db.query(StorePolicyDB).filter(StorePolicyDB.is_deleted == False).offset(skip).limit(limit).all()
    return policies

@app.get("/policies/{policy_id}", response_model=StorePolicy)
def read_policy(policy_id: int, db: Session = Depends(get_db)):
    policy = db.query(StorePolicyDB).filter(StorePolicyDB.policy_id == policy_id, StorePolicyDB.is_deleted == False).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy

@app.post("/policies/", response_model=StorePolicy)
def create_policy(policy: StorePolicyCreate, db: Session = Depends(get_db), q_client = Depends(get_qdrant_db_client)):
    db_policy = StorePolicyDB(**policy.model_dump())
    db.add(db_policy)
    db.commit()
    db.refresh(db_policy)
    # Sync with Qdrant
    if q_client:
        try:
            update_policy_in_qdrant(q_client, db_policy.policy_id, policy.model_dump())
        except Exception as e:
            logger.error(f"Failed to sync new policy {db_policy.policy_id} to Qdrant: {e}", exc_info=True)
    return db_policy

@app.put("/policies/{policy_id}", response_model=StorePolicy)
def update_policy(policy_id: int, policy: StorePolicyCreate, db: Session = Depends(get_db), q_client = Depends(get_qdrant_db_client)):
    db_policy = db.query(StorePolicyDB).filter(StorePolicyDB.policy_id == policy_id, StorePolicyDB.is_deleted == False).first()
    if not db_policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    for key, value in policy.model_dump(exclude_unset=True).items(): # exclude_unset for partial updates
        setattr(db_policy, key, value)
    db.commit()
    db.refresh(db_policy)
    # Sync with Qdrant
    if q_client:
        try:
            update_policy_in_qdrant(q_client, policy_id, policy.model_dump())
        except Exception as e:
            logger.error(f"Failed to sync updated policy {policy_id} to Qdrant: {e}", exc_info=True)
    return db_policy

@app.delete("/policies/{policy_id}", response_model=StorePolicy)
def delete_policy(policy_id: int, db: Session = Depends(get_db), q_client = Depends(get_qdrant_db_client)):
    db_policy = db.query(StorePolicyDB).filter(StorePolicyDB.policy_id == policy_id, StorePolicyDB.is_deleted == False).first()
    if not db_policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    db_policy.is_deleted = True #soft delete
    db.commit()
    db.refresh(db_policy)
    # Sync with Qdrant (delete)
    if q_client:
        try:
            delete_policy_from_qdrant(q_client, policy_id)
        except Exception as e:
            logger.error(f"Failed to delete policy {policy_id} from Qdrant: {e}", exc_info=True)
    return db_policy
