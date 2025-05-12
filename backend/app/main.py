from fastapi import FastAPI, HTTPException, Depends, Query
from typing import List, Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import Session
from backend.app.config import DATABASE_URL
from backend.app.models import Product, ProductCreate, ProductDB, Review, ReviewCreate, ReviewDB, StorePolicy, StorePolicyCreate, StorePolicyDB, Base  # Import from models.py
from datetime import datetime

# --- SQLAlchemy Setup ---
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
#Base = declarative_base() # Removed
Base.metadata.create_all(bind=engine) #creates the tables


# --- FastAPI App ---
app = FastAPI()


# --- Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    db_product = ProductDB(**product.dict())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

@app.put("/products/{product_id}", response_model=Product)
def update_product(product_id: str, product: ProductCreate, db: Session = Depends(get_db)):
    db_product = db.query(ProductDB).filter(ProductDB.product_id == product_id, ProductDB.is_deleted == False).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    for key, value in product.dict().items():
        setattr(db_product, key, value)
    db.commit()
    db.refresh(db_product)
    return db_product

@app.delete("/products/{product_id}", response_model=Product)
def delete_product(product_id: str, db: Session = Depends(get_db)):
    db_product = db.query(ProductDB).filter(ProductDB.product_id == product_id, ProductDB.is_deleted == False).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    db_product.is_deleted = True #soft delete
    db.commit()
    db.refresh(db_product)
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
def create_review(review: ReviewCreate, db: Session = Depends(get_db)):
    # Check if the product exists
    product = db.query(ProductDB).filter(ProductDB.product_id == review.product_id, ProductDB.is_deleted == False).first()
    if not product:
        raise HTTPException(status_code=400, detail="Product not found")

    db_review = ReviewDB(**review.dict())
    db.add(db_review)
    db.commit()
    db.refresh(db_review)
    return db_review

@app.put("/reviews/{review_id}", response_model=Review)
def update_review(review_id: int, review: ReviewCreate, db: Session = Depends(get_db)):
    db_review = db.query(ReviewDB).filter(ReviewDB.review_id == review_id, ReviewDB.is_deleted == False).first()
    if not db_review:
        raise HTTPException(status_code=404, detail="Review not found")
    for key, value in review.dict().items():
        setattr(db_review, key, value)
    db.commit()
    db.refresh(db_review)
    return db_review

@app.delete("/reviews/{review_id}", response_model=Review)
def delete_review(review_id: int, db: Session = Depends(get_db)):
    db_review = db.query(ReviewDB).filter(ReviewDB.review_id == review_id, ReviewDB.is_deleted == False).first()
    if not db_review:
        raise HTTPException(status_code=404, detail="Review not found")
    db_review.is_deleted = True #soft delete
    db.commit()
    db.refresh(db_review)
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
def create_policy(policy: StorePolicyCreate, db: Session = Depends(get_db)):
    db_policy = StorePolicyDB(**policy.dict())
    db.add(db_policy)
    db.commit()
    db.refresh(db_policy)
    return db_policy

@app.put("/policies/{policy_id}", response_model=StorePolicy)
def update_policy(policy_id: int, policy: StorePolicyCreate, db: Session = Depends(get_db)):
    db_policy = db.query(StorePolicyDB).filter(StorePolicyDB.policy_id == policy_id, StorePolicyDB.is_deleted == False).first()
    if not db_policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    for key, value in policy.dict().items():
        setattr(db_policy, key, value)
    db.commit()
    db.refresh(db_policy)
    return db_policy

@app.delete("/policies/{policy_id}", response_model=StorePolicy)
def delete_policy(policy_id: int, db: Session = Depends(get_db)):
    db_policy = db.query(StorePolicyDB).filter(StorePolicyDB.policy_id == policy_id, db.is_deleted == False).first()
    if not db_policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    db_policy.is_deleted = True #soft delete
    db.commit()
    db.refresh(db_policy)
    return db_policy
