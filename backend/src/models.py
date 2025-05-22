from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship, declarative_base, Mapped, mapped_column
from sqlalchemy.sql import func
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Any # Added Any for SearchResultItem.retrieved_item
from datetime import datetime

# --- SQLAlchemy Base ---
Base = declarative_base()

# --- Pydantic Models (Schemas for API requests and responses) ---

# Pydantic V2 model configuration
MODEL_CONFIG = ConfigDict(from_attributes=True)

# Base Pydantic model for ORM compatibility
class OrmBaseModel(BaseModel):
    model_config = MODEL_CONFIG


# Product Schemas
class ProductBase(OrmBaseModel):
    name: str
    description: Optional[str] = None
    price: float = Field(..., gt=0)
    category: Optional[str] = None
    brand: Optional[str] = None
    stock: Optional[int] = Field(None, ge=0)
    rating: Optional[float] = Field(None, ge=0, le=5)

class ProductCreate(ProductBase):
    # Explicitly define all fields required in the POST request body
    product_id: str # This is the primary key and must be provided for creation
    # name, description, price, etc., are inherited from ProductBase
    # and their optionality/requirements are defined there or overridden here if needed.


class Product(ProductBase):
    product_id: str # Include product_id in the response model
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_deleted: bool = False


# Review Schemas
class ReviewBase(OrmBaseModel):
    product_id: str # Foreign key to Product
    user_id: str # Assuming user_id is a string, adjust if it's an int
    rating: int = Field(..., ge=1, le=5)
    text: Optional[str] = None

class ReviewCreate(ReviewBase):
    # All fields from ReviewBase are inherited and their requirements are defined there.
    # No need to redefine unless overriding behavior.
    pass

class Review(ReviewBase):
    review_id: int # Primary key
    review_date: Optional[datetime] = None # Assuming this can be null or set by DB
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_deleted: bool = False


# Store Policy Schemas
class StorePolicyBase(OrmBaseModel):
    policy_type: str
    description: str
    conditions: Optional[str] = None
    timeframe: Optional[str] = None

class StorePolicyCreate(StorePolicyBase):
    # All fields from StorePolicyBase are inherited.
    pass

class StorePolicy(StorePolicyBase):
    policy_id: int # Primary key
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_deleted: bool = False


# --- Search Schemas ---
class SearchQuery(BaseModel):
    query: str = Field(..., min_length=1, description="The search query text.")
    limit: int = Field(10, ge=1, le=100, description="Maximum number of results to return.")
    # Optional: Add filters like specific collections to search
    # search_in_products: bool = True
    # search_in_reviews: bool = True
    # search_in_policies: bool = True

class SearchResultItem(BaseModel):
    score: Optional[float] = Field(None, description="Relevance score from the vector search (if applicable).")
    source_collection: Optional[str] = Field(None, description="The Qdrant collection the result came from (if applicable).")
    payload: Optional[dict] = Field(None, description="The payload of the Qdrant point (if applicable).")
    retrieved_item: Optional[Any] = Field(None, description="The full item retrieved from PostgreSQL (Product, Review, or StorePolicy).")

class SearchResponse(BaseModel):
    query_type: str = Field(..., description="Type of query processed (e.g., 'product_id_lookup', 'semantic_search_rag').")
    llm_answer: Optional[str] = Field(None, description="LLM generated answer for semantic search queries.")
    direct_product_result: Optional[Product] = Field(None, description="Direct product result if query was a product ID.")
    results: List[SearchResultItem] = Field(default_factory=list, description="List of source documents or search results.")


# --- SQLAlchemy ORM Models (Database table definitions) ---

class ProductDB(Base):
    __tablename__ = "products"

    product_id = Column(String, primary_key=True, index=True) # E.g., "SP0001"
    name = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    category = Column(String, index=True, nullable=True)
    brand = Column(String, index=True, nullable=True)
    stock = Column(Integer, nullable=True)
    rating = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_deleted = Column(Boolean, default=False, nullable=False)

    reviews = relationship("ReviewDB", back_populates="product")


class ReviewDB(Base):
    __tablename__ = "reviews"

    review_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    product_id = Column(String, ForeignKey("products.product_id"), nullable=False)
    user_id = Column(String, nullable=False) # Assuming user_id is a string
    rating = Column(Integer, nullable=False)
    text = Column(Text, nullable=True)
    review_date = Column(DateTime(timezone=True), server_default=func.now()) # Or allow null if provided by user
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_deleted = Column(Boolean, default=False, nullable=False)
    product = relationship("ProductDB", back_populates="reviews")


class StorePolicyDB(Base):
    __tablename__ = "store_policies"

    policy_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    policy_type = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=False)
    conditions = Column(Text, nullable=True)
    timeframe = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_deleted = Column(Boolean, default=False, nullable=False)

