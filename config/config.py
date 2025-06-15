import os
from dotenv import load_dotenv

import torch # For device detection
from sentence_transformers import SentenceTransformer # For loading the model
from qdrant_client import QdrantClient # For Qdrant client
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

# --- Embedding Service Configuration ---
EMBEDDING_SERVICE_URL = os.getenv('EMBEDDING_SERVICE_URL')
if not EMBEDDING_SERVICE_URL:
    raise EnvironmentError(
        "Missing EMBEDDING_SERVICE_URL environment variable. "
        "Ensure it is set in your .env file or system environment."
    )

# --- Vector DB (Qdrant) Configuration ---
VECTOR_DB_HOST = os.getenv('VECTOR_DB_HOST')
VECTOR_DB_PORT_STR = os.getenv('VECTOR_DB_PORT')
VECTOR_DB_COLLECTION_PRODUCTS = os.getenv('VECTOR_DB_COLLECTION_PRODUCTS', 'products_collection') # Default can be acceptable here
VECTOR_DB_COLLECTION_REVIEWS = os.getenv('VECTOR_DB_COLLECTION_REVIEWS', 'reviews_collection')   # Default can be acceptable here
VECTOR_DB_COLLECTION_POLICIES = os.getenv('VECTOR_DB_COLLECTION_POLICIES', 'policies_collection') # Default can be acceptable here

SENTENCE_TRANSFORMER_MODEL = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_DEFAULT_MODEL = os.getenv("OPENAI_DEFAULT_MODEL", "gpt-3.5-turbo")

# --- Redis Configuration ---
REDIS_HOST = os.getenv("REDIS_HOST", "redis") # Default to service name in Docker
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}"

# --- Embedding Model Configuration and Loading ---
# Define a cache folder for sentence-transformers models within the container
# This path should be mounted as a volume in Docker Compose for persistence and sharing
MODEL_CACHE_FOLDER = os.getenv('MODEL_CACHE_FOLDER', '/app/model_cache') # Default if not set

# Determine the device to use (GPU if available, otherwise CPU)
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'

# Global variable to hold the cached model instance
_cached_embedding_model = None

def get_embedding_model() -> SentenceTransformer:
    """Loads and caches the SentenceTransformer model."""
    global _cached_embedding_model
    if _cached_embedding_model is None:
        try:
            # When running in Docker, HF_HOME is set in the Dockerfile.
            # SentenceTransformer will use HF_HOME by default if cache_folder is None.
            # For local non-Docker runs, it will use its default user cache.
            
            print(f"CONFIG.PY: Attempting to load SentenceTransformer model '{SENTENCE_TRANSFORMER_MODEL}' on device '{DEVICE}'.")
            # Log the relevant cache environment variables to confirm they are set as expected inside the container.
            hf_home_path = os.getenv('HF_HOME')
            transformers_cache_path = os.getenv('TRANSFORMERS_CACHE')
            print(f"CONFIG.PY: HF_HOME is set to: {hf_home_path}")
            print(f"CONFIG.PY: TRANSFORMERS_CACHE is set to: {transformers_cache_path}")
            print(f"CONFIG.PY: MODEL_CACHE_FOLDER (from .env, for volume mount reference) is: {MODEL_CACHE_FOLDER}")

            # By passing cache_folder=None, SentenceTransformer should respect HF_HOME/TRANSFORMERS_CACHE.
            # The mkdir and chmod in the Dockerfile should ensure HF_HOME is writable.
            _cached_embedding_model = SentenceTransformer(SENTENCE_TRANSFORMER_MODEL, device=DEVICE, cache_folder=None)
            
            print("CONFIG.PY: SentenceTransformer model loaded successfully.")
        except Exception as e:
            print(f"CONFIG.PY: CRITICAL ERROR loading SentenceTransformer model '{SENTENCE_TRANSFORMER_MODEL}': {e}")
            # Re-raise the exception. It will be caught by get_embeddings_for_texts in embedding_sync.py
            raise
    return _cached_embedding_model

# --- Qdrant Client Configuration and Loading ---
_cached_qdrant_client = None

def get_qdrant_client() -> QdrantClient:
    """Initializes and returns a Qdrant client, caching the instance."""
    global _cached_qdrant_client
    if _cached_qdrant_client is None:
        # VECTOR_DB_HOST and VECTOR_DB_PORT are validated below,
        # so they should be available here.
        try:
            # Use print for early logging before standard logging might be fully configured
            print(f"Attempting to initialize Qdrant client for host {VECTOR_DB_HOST}, configured port {VECTOR_DB_PORT}...")
            if VECTOR_DB_PORT == 6334: # Standard gRPC port
                print(f"Using gRPC port for Qdrant client: {VECTOR_DB_PORT}")
                _cached_qdrant_client = QdrantClient(host=VECTOR_DB_HOST, grpc_port=VECTOR_DB_PORT)
            elif VECTOR_DB_PORT == 6333: # Standard HTTP/REST port
                print(f"Using HTTP/REST port for Qdrant client: {VECTOR_DB_PORT}")
                _cached_qdrant_client = QdrantClient(host=VECTOR_DB_HOST, port=VECTOR_DB_PORT)
            else:
                # Fallback or if a full URL is preferred and configured differently
                print(f"Warning: Qdrant port {VECTOR_DB_PORT} is not standard 6333 or 6334. Assuming HTTP/REST on this port via URL.")
                _cached_qdrant_client = QdrantClient(url=f"http://{VECTOR_DB_HOST}:{VECTOR_DB_PORT}")
            _cached_qdrant_client.get_collections() # A simple way to test the connection
            print("Qdrant client initialized and connected successfully.")
        except Exception as e:
            print(f"Failed to initialize Qdrant client: {e}") # Use print for early logging
            raise # Re-raise to prevent app from starting with a bad client
    return _cached_qdrant_client

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
