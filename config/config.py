import os
from dotenv import load_dotenv

import torch # For device detection
from sentence_transformers import SentenceTransformer # For loading the model
# --- Project Root Configuration ---
# Assumes this config.py file is in <PROJECT_ROOT>/config/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- Load environment variables from project root .env file ---
dotenv_path = os.path.join(PROJECT_ROOT, '.env')
if not os.path.exists(dotenv_path):
    print(f"Warning: .env file not found at {dotenv_path}. Relying on environment variables set externally.")
load_dotenv(dotenv_path=dotenv_path)


# --- Database Configuration ---
DB_HOST = os.getenv('POSTGRES_HOST')
DB_PORT_STR = os.getenv('POSTGRES_PORT')
DB_NAME = os.getenv('POSTGRES_DB')
DB_USER = os.getenv('POSTGRES_USER')
DB_PASSWORD = os.getenv('POSTGRES_PASSWORD')


if not all([DB_HOST, DB_PORT_STR, DB_NAME, DB_USER, DB_PASSWORD]):
    raise EnvironmentError(
        "Missing one or more required PostgreSQL environment variables: "
        "POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD. "
        "Ensure they are set in your .env file or system environment."
    )
try:
    print(f'DB PORT Value {DB_PORT_STR}-finally')
    DB_PORT = int(DB_PORT_STR.strip())
except ValueError:
    raise EnvironmentError(f"POSTGRES_PORT environment variable ('{DB_PORT_STR}') must be an integer.")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# --- File Path Configurations ---
BASE_DATA_PATH = os.path.join(PROJECT_ROOT, 'data', 'raw')
PRODUCTS_CSV_PATH = os.path.join(BASE_DATA_PATH, 'products.csv')
REVIEWS_CSV_PATH = os.path.join(BASE_DATA_PATH, 'reviews.csv')
STORE_POLICIES_CSV_PATH = os.path.join(BASE_DATA_PATH, 'store_policies.csv')
INIT_SQL_PATH = os.path.join(PROJECT_ROOT, 'database', 'init.sql')

# # --- Embedding Service Configuration ---
# EMBEDDING_SERVICE_URL = os.getenv('EMBEDDING_SERVICE_URL')
# if not EMBEDDING_SERVICE_URL:
#     raise EnvironmentError(
#         "Missing EMBEDDING_SERVICE_URL environment variable. "
#         "Ensure it is set in your .env file or system environment."
#     )

# --- Vector DB (Qdrant) Configuration ---
VECTOR_DB_HOST = os.getenv('VECTOR_DB_HOST')
VECTOR_DB_PORT_STR = os.getenv('VECTOR_DB_PORT')
VECTOR_DB_COLLECTION_PRODUCTS = os.getenv('VECTOR_DB_COLLECTION_PRODUCTS', 'products_collection') # Default can be acceptable here
VECTOR_DB_COLLECTION_REVIEWS = os.getenv('VECTOR_DB_COLLECTION_REVIEWS', 'reviews_collection')   # Default can be acceptable here
VECTOR_DB_COLLECTION_POLICIES = os.getenv('VECTOR_DB_COLLECTION_POLICIES', 'policies_collection') # Default can be acceptable here

SENTENCE_TRANSFORMER_MODEL = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

# --- Embedding Model Configuration and Loading ---
# Define a cache folder for sentence-transformers models within the container
# This path should be mounted as a volume in Docker Compose for persistence and sharing
MODEL_CACHE_FOLDER = '/app/model_cache'

# Determine the device to use (GPU if available, otherwise CPU)
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'

# Global variable to hold the cached model instance
_cached_embedding_model = None

def get_embedding_model() -> SentenceTransformer:
    """Loads and caches the SentenceTransformer model."""
    global _cached_embedding_model
    if _cached_embedding_model is None:
        # Use print for early logging before standard logging might be fully configured
        print(f"Loading SentenceTransformer model '{SENTENCE_TRANSFORMER_MODEL}' on device '{DEVICE}' with cache '{MODEL_CACHE_FOLDER}'...")
        _cached_embedding_model = SentenceTransformer(SENTENCE_TRANSFORMER_MODEL, device=DEVICE, cache_folder=MODEL_CACHE_FOLDER)
        print("SentenceTransformer model loaded.")
    return _cached_embedding_model

# --- Validation Checks (Keep these after defining variables) ---
if not all([VECTOR_DB_HOST, VECTOR_DB_PORT_STR]):
    raise EnvironmentError(
        "Missing one or more required Vector DB environment variables: VECTOR_DB_HOST, VECTOR_DB_PORT. "
        "Ensure they are set in your .env file or system environment."
    )
try:
    VECTOR_DB_PORT = int(VECTOR_DB_PORT_STR)
except ValueError:
    raise EnvironmentError(f"VECTOR_DB_PORT environment variable ('{VECTOR_DB_PORT_STR}') must be an integer.")
