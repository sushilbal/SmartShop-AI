# SmartShop-AI/embedding_service/main.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from typing import List, Optional
import logging
import torch
import os

# --- Configuration ---
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Model Configuration
# You can make the model name an environment variable if you want to switch easily
DEFAULT_MODEL_NAME = 'all-MiniLM-L6-v2'
MODEL_NAME = os.getenv('EMBEDDING_MODEL_NAME', DEFAULT_MODEL_NAME)
# Optional: Define a cache folder for sentence-transformers models within the container
MODEL_CACHE_FOLDER = '/app/model_cache' # Ensure this path is writable

# --- FastAPI Application Setup ---
app = FastAPI(
    title="SmartShop AI Embedding Service",
    description="Provides text embeddings using a sentence transformer model.",
    version="0.1.0"
)

# --- Global Variables ---
model: Optional[SentenceTransformer] = None
device: Optional[str] = None

# --- Pydantic Models ---
class TextListInput(BaseModel):
    texts: List[str]
    # Example of adding more options if needed in the future
    # normalize_embeddings: bool = False

class EmbeddingResponse(BaseModel):
    embeddings: List[List[float]]
    model_name: str
    # texts_received: int
    # texts_embedded: int

class HealthResponse(BaseModel):
    status: str
    model_name: Optional[str] = None
    device: Optional[str] = None
    reason: Optional[str] = None

# --- Application Event Handlers ---
@app.on_event("startup")
async def startup_event():
    """
    Load the embedding model on application startup.
    """
    global model, device, MODEL_NAME
    try:
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        logger.info(f"Attempting to load embedding model '{MODEL_NAME}' on device '{device}'...")

        model = SentenceTransformer(MODEL_NAME, device=device, cache_folder=MODEL_CACHE_FOLDER)

        logger.info(f"Successfully loaded embedding model: '{MODEL_NAME}' on device '{device}'.")
    except Exception as e:
        logger.error(f"Fatal error loading embedding model '{MODEL_NAME}': {e}", exc_info=True)
        model = None # Mark model as not loaded

@app.on_event("shutdown")
async def shutdown_event():
    """
    Clean up resources on application shutdown.
    """
    global model
    logger.info("Shutting down embedding service.")
    if model:
        # SentenceTransformer models don't typically require explicit cleanup,
        # but if you had other resources (e.g., database connections), you'd clean them here.
        del model
        model = None
    logger.info("Embedding service shutdown complete.")


# --- API Endpoints ---
@app.post("/embed", response_model=EmbeddingResponse)
async def get_embeddings(data: TextListInput):
    """
    Generates embeddings for a list of input texts.
    """
    global model, MODEL_NAME
    if model is None:
        logger.error("Embedding model is not available. Startup might have failed.")
        raise HTTPException(status_code=503, detail="Embedding model not available or failed to load.")

    if not data.texts:
        return EmbeddingResponse(embeddings=[], model_name=MODEL_NAME)

    # Filter out any non-string or empty/whitespace-only strings to avoid errors with model.encode
    valid_texts_to_embed = [text for text in data.texts if isinstance(text, str) and text.strip()]

    if not valid_texts_to_embed:
        logger.info("Received request with no valid texts to embed after filtering.")
        # Return empty embeddings if all texts were invalid, matching the number of original texts if desired
        # or just an empty list for the valid ones. For simplicity, empty for valid ones:
        return EmbeddingResponse(embeddings=[], model_name=MODEL_NAME)

    try:
        logger.info(f"Embedding {len(valid_texts_to_embed)} valid texts (out of {len(data.texts)} received).")
        
        # Generate embeddings
        # For very long texts or large batches, this can be time-consuming.
        # Consider background tasks or async execution for production if latency is an issue.
        embedding_vectors = model.encode(valid_texts_to_embed, show_progress_bar=False)
        
        # The model.encode returns a list of numpy arrays or a single numpy array.
        # We need to convert them to a list of lists of floats for JSON serialization.
        embeddings_as_lists = [emb.tolist() for emb in embedding_vectors]

        logger.info(f"Successfully generated {len(embeddings_as_lists)} embeddings.")
        return EmbeddingResponse(embeddings=embeddings_as_lists, model_name=MODEL_NAME)

    except Exception as e:
        logger.error(f"Error generating embeddings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred while generating embeddings: {str(e)}")

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint to verify if the service and model are ready.
    """
    global model, MODEL_NAME, device
    if model:
        return HealthResponse(status="healthy", model_name=MODEL_NAME, device=device)
    else:
        return HealthResponse(status="unhealthy", reason="Embedding model not loaded or failed to load.", model_name=MODEL_NAME, device=device)

# To run this locally for testing (outside Docker, if needed):
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8001)