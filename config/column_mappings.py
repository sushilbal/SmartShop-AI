# /home/sushil/d-codebase/ProjectUp/SmartShopAI/SmartShop-AI/config/column_mappings.py
from .data_transformers import to_float_or_none, to_int_or_none

# Define mapping: (CSV_Header, DB_Column_Name, Transformation_Function_or_None)

PRODUCTS_COLUMN_MAP = [
    ('id', 'product_id', None),
    ('name', 'name', None),
    ('brand', 'brand', None),
    ('category', 'category', None),
    ('price', 'price', to_float_or_none),
    ('description', 'description', None),
    ('stock', 'stock', to_int_or_none),
    ('rating', 'rating', to_float_or_none)
]

STORE_POLICIES_COLUMN_MAP = [
    ('policy_type', 'policy_type', None),
    ('description', 'description', None),
    ('conditions', 'conditions', None),
    ('timeframe', 'timeframe', to_int_or_none)
]

REVIEWS_COLUMN_MAP = [
    ('product_id', 'product_id', None),
    ('rating', 'rating', to_float_or_none),
    ('text', 'text', None),
    ('date', 'review_date', None) # Assuming CSV 'date' is 'YYYY-MM-DD'
]

# Add mappings for other tables if they are populated from CSVs in the future.