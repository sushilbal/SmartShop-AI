from pydantic import BaseModel
from typing import List, Optional # Removed Text from here if it was only for Pydantic models
from sqlalchemy import Column, Integer, String, Text, DECIMAL, TIMESTAMP, Boolean, ForeignKey # Text is still needed for SQLAlchemy DB models
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()

# --- Pydantic Models ---
class ProductBase(BaseModel):
    name: str
    brand: Optional[str] = None
    category: Optional[str] = None
    price: float
    description: Optional[str] = None  # Changed from Text to str
    stock: Optional[int] = None
    rating: Optional[float] = None

class ProductCreate(ProductBase):
    product_id: str  # Changed to str to match the database

class Product(ProductBase):
    product_id: str
    created_at: datetime
    updated_at: Optional[datetime]
    is_deleted: bool

    class Config:
        orm_mode = True

class ReviewBase(BaseModel):
    product_id: str
    rating: float
    text: Optional[str] = None  # Changed from Text to str
    review_date: Optional[datetime]

class ReviewCreate(ReviewBase):
    pass

class Review(ReviewBase):
    review_id: int
    created_at: datetime
    updated_at: Optional[datetime]
    is_deleted: bool

    class Config:
        orm_mode = True

class StorePolicyBase(BaseModel):
    policy_type: str
    description: str # This was already str, which is good
    conditions: Optional[str] = None  # Changed from Text to str
    timeframe: Optional[int] = None

class StorePolicyCreate(StorePolicyBase):
    pass

class StorePolicy(StorePolicyBase):
    policy_id: int
    created_at: datetime
    updated_at: Optional[datetime]
    is_deleted: bool

    class Config:
        orm_mode = True

# --- SQLAlchemy Models ---
class ProductDB(Base):
    __tablename__ = "products"

    product_id = Column(String(20), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    brand = Column(String(255))
    category = Column(String(255))
    price = Column(DECIMAL, nullable=False)
    description = Column(Text)
    stock = Column(Integer)
    rating = Column(DECIMAL(2, 1))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)

    reviews = relationship("ReviewDB", back_populates="product")


class ReviewDB(Base):
    __tablename__ = "reviews"

    review_id = Column(Integer, primary_key=True, index=True)
    product_id = Column(String(20), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False)
    rating = Column(DECIMAL(2, 1), nullable=False)
    text = Column(Text)
    review_date = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)

    product = relationship("ProductDB", back_populates="reviews")


class StorePolicyDB(Base):
    __tablename__ = "store_policies"

    policy_id = Column(Integer, primary_key=True, index=True)
    policy_type = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    conditions = Column(Text)
    timeframe = Column(Integer)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)
