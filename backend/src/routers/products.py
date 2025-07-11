from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
import logging

from sqlalchemy.exc import IntegrityError

from src.models import Product, ProductCreate, ProductDB
from src.embedding_sync import update_product_in_qdrant, delete_product_from_qdrant
from src.dependencies import get_db, get_qdrant_db_client
from src.utils import get_obj_or_404

router = APIRouter(
    prefix="/products",
    tags=["products"],
)

logger = logging.getLogger(__name__)

@router.get("/", response_model=List[Product])
def read_products(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    products = db.query(ProductDB).filter(ProductDB.is_deleted == False).offset(skip).limit(limit).all()
    return products

@router.get("/{product_id}", response_model=Product)
def read_product(product_id: str, db: Session = Depends(get_db)):
    return get_obj_or_404(db, ProductDB, product_id, action="read")

@router.post("/", response_model=Product)
def create_product(
    product: ProductCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    q_client = Depends(get_qdrant_db_client)
):
    try:
        db_product = ProductDB(**product.model_dump())
        db.add(db_product)
        db.commit()
        db.refresh(db_product)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Product with ID '{product.product_id}' already exists or violates a unique constraint.")

    if q_client:
        # Qdrant update will now run in the background
        # Assumes update_product_in_qdrant handles its own exceptions and logging
        background_tasks.add_task(update_product_in_qdrant, q_client, db_product.product_id, product.model_dump())
    return db_product

@router.put("/{product_id}", response_model=Product)
def update_product(
    product_id: str,
    product: ProductCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    q_client = Depends(get_qdrant_db_client)
):
    db_product = get_obj_or_404(db, ProductDB, product_id, action="update")
    for key, value in product.model_dump(exclude_unset=True).items():
        setattr(db_product, key, value)
    db.commit()
    db.refresh(db_product)
    if q_client:
        background_tasks.add_task(update_product_in_qdrant, q_client, product_id, product.model_dump())
    return db_product

@router.delete("/{product_id}", response_model=Product)
def delete_product(
    product_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    q_client = Depends(get_qdrant_db_client)
):
    db_product = get_obj_or_404(db, ProductDB, product_id, action="delete")
    db_product.is_deleted = True
    db.commit()
    db.refresh(db_product)
    if q_client:
        background_tasks.add_task(delete_product_from_qdrant, q_client, product_id)
    return db_product