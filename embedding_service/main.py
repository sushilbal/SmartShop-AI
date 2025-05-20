# SmartShop-AI/embedding_service/main.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from typing import List, Optional
import torch # Still needed for HealthResponse device info
import logging

# Import centralized config and model loading function
from config.config import get_embedding_model, SENTENCE_TRANSFORMER_MODEL, DEVICE

# --- Configuration ---
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- FastAPI Application Setup ---
app = FastAPI(
    title="SmartShop AI Embedding Service",
    description="Provides text embeddings using a sentence transformer model.",
    version="0.1.0"
)

# --- Global Variables ---
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
    # The model loading is now handled by the centralized config function
    try:
        # Call the centralized function to get the model instance
        model = get_embedding_model()
        device = DEVICE # Get the determined device from config
        logger.info(f"Embedding model '{SENTENCE_TRANSFORMER_MODEL}' loaded via config on device '{DEVICE}'.")
    except Exception as e:
        logger.error(f"Fatal error loading embedding model via config: {e}", exc_info=True)
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
    global model, SENTENCE_TRANSFORMER_MODEL # Use the model name from config
    if model is None:
        logger.error("Embedding model is not available. Startup might have failed.")
        raise HTTPException(status_code=503, detail="Embedding model not available or failed to load.")

    if not data.texts:
        return EmbeddingResponse(embeddings=[], model_name=MODEL_NAME)

    # Filter out any non-string or empty/whitespace-only strings
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
    # Use the model name and device from config
    if model:
        return HealthResponse(status="healthy", model_name=SENTENCE_TRANSFORMER_MODEL, device=DEVICE)
    else:
        return HealthResponse(status="unhealthy", reason="Embedding model not loaded or failed to load.", model_name=SENTENCE_TRANSFORMER_MODEL, device=DEVICE)

# To run this locally for testing (outside Docker, if needed):
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8001)