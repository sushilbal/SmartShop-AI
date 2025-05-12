# /home/sushil/d-codebase/ProjectUp/SmartShopAI/SmartShop-AI/config/data_transformers.py

def to_float_or_none(value_str):
    """Converts a string to float, returns None if empty or invalid."""
    if value_str and value_str.strip():
        try:
            return float(value_str)
        except ValueError:
            return None
    return None

def to_int_or_none(value_str):
    """Converts a string to int, returns None if empty or invalid."""
    if value_str and value_str.strip():
        try:
            return int(value_str)
        except ValueError:
            return None
    return None

# Add any other general-purpose data transformers here if needed in the future.