import logging
import uuid # For generating Qdrant point IDs if needed
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient, models as qdrant_models
from config.config import (
    # EMBEDDING_SERVICE_URL, # No longer used as we use local sentence transformers
    VECTOR_DB_COLLECTION_PRODUCTS,
    VECTOR_DB_COLLECTION_REVIEWS,
    VECTOR_DB_COLLECTION_POLICIES,
    get_embedding_model # Import the centralized model loader
)


logger = logging.getLogger(__name__)

def get_embeddings_for_texts(texts: List[str]) -> Optional[List[List[float]]]:
    if not texts:
        return []
    print(f"DEBUG: EMBEDDING_SYNC.PY (get_embeddings_for_texts): Received texts: {texts}")
    try:
        # Use the centralized embedding model
        print(f"DEBUG: EMBEDDING_SYNC.PY (get_embeddings_for_texts): Calling get_embedding_model()...")
        model_instance = get_embedding_model()
        if model_instance is None: # Should not happen if config.py's get_embedding_model raises on failure
            logger.error("Embedding model instance is None. Cannot generate embeddings.")
            print("DEBUG: EMBEDDING_SYNC.PY (get_embeddings_for_texts): ERROR - model_instance is None. Returning None.")
            return None
        
        print(f"DEBUG: EMBEDDING_SYNC.PY (get_embeddings_for_texts): Encoding {len(texts)} texts with model...")
        embeddings_np = model_instance.encode(texts, show_progress_bar=False)
        result = embeddings_np.tolist()
        print(f"DEBUG: EMBEDDING_SYNC.PY (get_embeddings_for_texts): Embeddings generated. Shape: {embeddings_np.shape if hasattr(embeddings_np, 'shape') else 'N/A'}. Returning {len(result)} embeddings.")
        return result
    except Exception as e:
        logger.error(f"Error generating embeddings locally: {e}", exc_info=True)
        print(f"DEBUG: EMBEDDING_SYNC.PY (get_embeddings_for_texts): EXCEPTION during embedding generation: {e}. Returning None.")
        return None

# --- Helper: Text Chunking (if needed before embedding certain fields) ---
# You might put your chunk_text_into_sentences function here or import it
# from a shared utility module if it's also used in populate_db.py
try:
    import pysbd
    def chunk_text(text: str, language="en") -> List[str]:
        if not text or not text.strip():
            return []
        try:
            segmenter = pysbd.Segmenter(language=language, clean=False)
            return segmenter.segment(text)
        except Exception as e:
            logger.warning(f"PySBD chunking failed: {e}. Falling back to single chunk.")
            return [text] if text and text.strip() else []
except ImportError:
    logger.warning("pysbd not installed. Chunking will be basic (whole text).")
    def chunk_text(text: str, language="en") -> List[str]: # Fallback
        return [text] if text and text.strip() else []


# --- Product Vector Operations ---
def update_product_in_qdrant(
    q_client: QdrantClient,
    product_id: str, # This is the ID from PostgreSQL
    product_data: Dict[str, Any] # Data from the Product Pydantic model
):
    try:
        print(f"DEBUG: EMBEDDING_SYNC.PY (update_product_in_qdrant): Starting for product_id: {product_id}, data: {product_data}")
        logger.info(f"Updating/creating product {product_id} in Qdrant.")
        # Ensure we only join non-empty, stripped strings
        name_part = product_data.get('name', '').strip()
        brand_part = f"Brand: {product_data.get('brand', '').strip()}" if product_data.get('brand', '').strip() else ""
        category_part = f"Category: {product_data.get('category', '').strip()}" if product_data.get('category', '').strip() else ""
        description_part = product_data.get('description', '').strip()

        text_to_embed = ". ".join(filter(None, [name_part, brand_part, category_part, description_part])).strip()

        print(f"DEBUG: EMBEDDING_SYNC.PY (update_product_in_qdrant): Text to embed for product {product_id}: '{text_to_embed}'")

        if not text_to_embed:
            logger.warning(f"No text content to embed for product {product_id}. Skipping Qdrant update.")
            print(f"DEBUG: EMBEDDING_SYNC.PY (update_product_in_qdrant): No text to embed for product {product_id}. Returning.")
            return

        # For products, assume one primary embedding (or first chunk if chunking strategy is defined)
        # If chunking products: Implement chunking logic here or pass pre-chunked data
        print(f"DEBUG: EMBEDDING_SYNC.PY (update_product_in_qdrant): Calling get_embeddings_for_texts for product {product_id}...")
        embeddings = get_embeddings_for_texts([text_to_embed])
        print(f"DEBUG: EMBEDDING_SYNC.PY (update_product_in_qdrant): Embeddings received for product {product_id}: {'Exists' if embeddings and embeddings[0] else 'None or Empty'}")
        if not embeddings or not embeddings[0]:
            logger.error(f"Failed to get embedding for product {product_id}")
            print(f"DEBUG: EMBEDDING_SYNC.PY (update_product_in_qdrant): Failed to get embeddings for product {product_id}. Returning.")
            return

        vector = embeddings[0]
        payload = {
            "name": product_data.get('name'),
            "brand": product_data.get('brand'),
            "category": product_data.get('category'),
            "price": product_data.get('price'),
            "rating": product_data.get('rating'),
            "source_text_snippet": text_to_embed[:250] # Store a snippet
        }
        
        # Qdrant ID: Use the product_id from PostgreSQL directly if it's an integer or UUID.
        # If product_id is a string like "SP0001", Qdrant needs an integer or UUID.
        # For consistency with how populate_db.py handles it: if product_id is not int/UUID,
        # generate a deterministic UUID from it or use a mapping.
        # Simplest approach if product_id is always an INT after mapping in PG:
        # qdrant_id = int(product_id)
        # If product_id from your DB is a string like "SP0001", you need to convert it.
        # Let's assume for now you use a UUID derived from your string product_id.
        qdrant_id_to_use = str(uuid.uuid5(uuid.NAMESPACE_DNS, product_id))
        print(f"DEBUG: EMBEDDING_SYNC.PY (update_product_in_qdrant): Qdrant ID for product {product_id} will be {qdrant_id_to_use}")


        print(f"DEBUG: EMBEDDING_SYNC.PY (update_product_in_qdrant): Calling q_client.upsert for product {product_id}...")
        q_client.upsert(
            collection_name=VECTOR_DB_COLLECTION_PRODUCTS,
            points=[qdrant_models.PointStruct(id=qdrant_id_to_use, vector=vector, payload=payload)]
        )
        print(f"DEBUG: EMBEDDING_SYNC.PY (update_product_in_qdrant): q_client.upsert call completed for product {product_id}.")
        logger.info(f"Successfully upserted product {product_id} (Qdrant ID: {qdrant_id_to_use}) to Qdrant.")
    except Exception as e:
        logger.error(f"Error updating product {product_id} in Qdrant: {e}", exc_info=True)
        print(f"DEBUG: EMBEDDING_SYNC.PY (update_product_in_qdrant): EXCEPTION for product {product_id}: {e}")

def delete_product_from_qdrant(q_client: QdrantClient, product_id: str):
    try:
        print(f"DEBUG: EMBEDDING_SYNC.PY (delete_product_from_qdrant): Deleting product {product_id}")
        logger.info(f"Deleting product {product_id} from Qdrant.")
        qdrant_id_to_use = str(uuid.uuid5(uuid.NAMESPACE_DNS, product_id)) # Must match the ID used for upsert
        q_client.delete(
            collection_name=VECTOR_DB_COLLECTION_PRODUCTS,
            points_selector=qdrant_models.PointIdsList(points=[qdrant_id_to_use])
        )
        logger.info(f"Successfully deleted product {product_id} (Qdrant ID: {qdrant_id_to_use}) from Qdrant.")
    except Exception as e:
        logger.error(f"Error deleting product {product_id} from Qdrant: {e}", exc_info=True)
        print(f"DEBUG: EMBEDDING_SYNC.PY (delete_product_from_qdrant): EXCEPTION for product {product_id}: {e}")

# --- Review Vector Operations ---
def update_review_in_qdrant(
    q_client: QdrantClient,
    review_id: int, # This is the PostgreSQL SERIAL ID (unsigned integer)
    review_data: Dict[str, Any] # Contains 'text', 'product_id', 'rating'
):
    try:
        print(f"DEBUG: EMBEDDING_SYNC.PY (update_review_in_qdrant): Starting for review_id: {review_id}, data: {review_data}")
        logger.info(f"Updating/creating review {review_id} in Qdrant.")
        review_text = review_data.get("text", "")
        print(f"DEBUG: EMBEDDING_SYNC.PY (update_review_in_qdrant): Review text for review {review_id}: '{review_text[:100]}...'") # Print snippet
        if not review_text.strip():
            logger.warning(f"Review {review_id} has no text. Skipping Qdrant update.")
            print(f"DEBUG: EMBEDDING_SYNC.PY (update_review_in_qdrant): No text for review {review_id}. Returning.")
            return

        # For reviews, usually embed the whole text (unless very long)
        # If you decide to chunk reviews here, apply chunking logic and loop
        chunks = chunk_text(review_text) # Using the helper for consistency
        points_to_upsert = []

        for chunk_idx, chunk_text_content in enumerate(chunks):
            print(f"DEBUG: EMBEDDING_SYNC.PY (update_review_in_qdrant): Processing chunk {chunk_idx} for review {review_id}. Calling get_embeddings_for_texts...")
            embeddings = get_embeddings_for_texts([chunk_text_content])
            print(f"DEBUG: EMBEDDING_SYNC.PY (update_review_in_qdrant): Embeddings received for review {review_id}, chunk {chunk_idx}: {'Exists' if embeddings and embeddings[0] else 'None or Empty'}")
            if not embeddings or not embeddings[0]:
                logger.error(f"Failed to get embedding for review {review_id}, chunk {chunk_idx}")
                print(f"DEBUG: EMBEDDING_SYNC.PY (update_review_in_qdrant): Failed to get embeddings for review {review_id}, chunk {chunk_idx}. Continuing to next chunk.")
                continue
            
            vector = embeddings[0]
            # For chunks, each chunk needs a unique ID.
            # The main review_id from PG is an int, so it can be used directly if not chunking.
            # If chunking, generate UUIDs for each chunk.
            qdrant_point_id = f"{review_id}_chunk_{chunk_idx}" # This was an issue before.
                                                            # MUST be int or UUID.
            qdrant_point_id = str(uuid.uuid4()) # Correct approach for chunk IDs

            payload = {
                "original_review_id": review_id,
                "product_id": review_data.get("product_id"),
                "rating": review_data.get("rating"),
                "chunk_index": chunk_idx,
                "text_chunk": chunk_text_content
            }
            points_to_upsert.append(qdrant_models.PointStruct(id=qdrant_point_id, vector=vector, payload=payload))

        if points_to_upsert:
            print(f"DEBUG: EMBEDDING_SYNC.PY (update_review_in_qdrant): Calling q_client.upsert for {len(points_to_upsert)} chunks for review {review_id}...")
            q_client.upsert(
                collection_name=VECTOR_DB_COLLECTION_REVIEWS,
                points=points_to_upsert
            )
            print(f"DEBUG: EMBEDDING_SYNC.PY (update_review_in_qdrant): q_client.upsert call completed for review {review_id}.")
            logger.info(f"Successfully upserted {len(points_to_upsert)} chunk(s) for review {review_id} to Qdrant.")
        else:
            print(f"DEBUG: EMBEDDING_SYNC.PY (update_review_in_qdrant): No points to upsert for review {review_id}.")
    except Exception as e:
        logger.error(f"Error updating review {review_id} in Qdrant: {e}", exc_info=True)
        print(f"DEBUG: EMBEDDING_SYNC.PY (update_review_in_qdrant): EXCEPTION for review {review_id}: {e}")

def delete_review_from_qdrant(q_client: QdrantClient, review_id: int):
    try:
        print(f"DEBUG: EMBEDDING_SYNC.PY (delete_review_from_qdrant): Deleting review {review_id}")
        logger.info(f"Deleting review {review_id} (and its chunks) from Qdrant.")
        # If you used UUIDs for chunks, you'd delete by filtering on "original_review_id" in payload
        q_client.delete(
            collection_name=VECTOR_DB_COLLECTION_REVIEWS,
            points_selector=qdrant_models.FilterSelector(filter=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(key="original_review_id", match=qdrant_models.MatchValue(value=review_id))
                ]
            ))
        )
        # If you stored one vector per review using review_id as Qdrant ID:
        # q_client.delete(
        #     collection_name="reviews_collection",
        #     points_selector=qdrant_models.PointIdsList(points=[review_id])
        # )
        logger.info(f"Successfully deleted review {review_id} (and its chunks) from Qdrant.")
    except Exception as e:
        logger.error(f"Error deleting review {review_id} from Qdrant: {e}", exc_info=True)
        print(f"DEBUG: EMBEDDING_SYNC.PY (delete_review_from_qdrant): EXCEPTION for review {review_id}: {e}")

# --- Store Policy Vector Operations (similar to reviews, likely involves chunking) ---
def update_policy_in_qdrant(
    q_client: QdrantClient,
    policy_id: int, # PostgreSQL SERIAL ID
    policy_data: Dict[str, Any]
):
    try:
        print(f"DEBUG: EMBEDDING_SYNC.PY (update_policy_in_qdrant): Starting for policy_id: {policy_id}, data: {policy_data}")
        logger.info(f"Updating/creating policy {policy_id} in Qdrant.")
        
        text_parts = []
        policy_type = policy_data.get("policy_type", "")
        description = policy_data.get("description", "")
        # conditions = policy_data.get("conditions", "") # Assuming conditions might also be text for embedding

        if policy_type.strip():
            text_parts.append(f"Policy Type: {policy_type.strip()}")
        if description.strip():
            text_parts.append(description.strip())
        # if conditions.strip():
        #     text_parts.append(f"Conditions: {conditions.strip()}")
            
        text_to_embed = ". ".join(filter(None, text_parts)).strip()
        print(f"DEBUG: EMBEDDING_SYNC.PY (update_policy_in_qdrant): Text to embed for policy {policy_id}: '{text_to_embed}'")

        if not text_to_embed:
            logger.warning(f"Policy {policy_id} has no text content to embed. Skipping Qdrant update.")
            print(f"DEBUG: EMBEDDING_SYNC.PY (update_policy_in_qdrant): No text to embed for policy {policy_id}. Returning.")
            return

        chunks = chunk_text(text_to_embed)
        points_to_upsert = []

        for chunk_idx, chunk_text_content in enumerate(chunks):
            print(f"DEBUG: EMBEDDING_SYNC.PY (update_policy_in_qdrant): Processing chunk {chunk_idx} for policy {policy_id}. Calling get_embeddings_for_texts...")
            embeddings = get_embeddings_for_texts([chunk_text_content])
            print(f"DEBUG: EMBEDDING_SYNC.PY (update_policy_in_qdrant): Embeddings received for policy {policy_id}, chunk {chunk_idx}: {'Exists' if embeddings and embeddings[0] else 'None or Empty'}")
            if not embeddings or not embeddings[0]:
                logger.error(f"Failed to get embedding for policy {policy_id}, chunk {chunk_idx}")
                print(f"DEBUG: EMBEDDING_SYNC.PY (update_policy_in_qdrant): Failed to get embeddings for policy {policy_id}, chunk {chunk_idx}. Continuing to next chunk.")
                continue
            
            vector = embeddings[0]
            qdrant_point_id = str(uuid.uuid4()) # Unique ID for each chunk

            payload = {
                "original_policy_id": policy_id,
                "policy_type": policy_data.get("policy_type"),
                "conditions": policy_data.get("conditions"), # Store original conditions
                "timeframe": policy_data.get("timeframe"),
                "chunk_index": chunk_idx,
                "text_chunk": chunk_text_content
            }
            points_to_upsert.append(qdrant_models.PointStruct(id=qdrant_point_id, vector=vector, payload=payload))

        if points_to_upsert:
            print(f"DEBUG: EMBEDDING_SYNC.PY (update_policy_in_qdrant): Calling q_client.upsert for {len(points_to_upsert)} chunks for policy {policy_id}...")
            q_client.upsert(
                collection_name=VECTOR_DB_COLLECTION_POLICIES,
                points=points_to_upsert
            )
            print(f"DEBUG: EMBEDDING_SYNC.PY (update_policy_in_qdrant): q_client.upsert call completed for policy {policy_id}.")
            logger.info(f"Successfully upserted {len(points_to_upsert)} chunk(s) for policy {policy_id} to Qdrant.")
        else:
            print(f"DEBUG: EMBEDDING_SYNC.PY (update_policy_in_qdrant): No points to upsert for policy {policy_id}.")
    except Exception as e:
        logger.error(f"Error updating policy {policy_id} in Qdrant: {e}", exc_info=True)
        print(f"DEBUG: EMBEDDING_SYNC.PY (update_policy_in_qdrant): EXCEPTION for policy {policy_id}: {e}")

def delete_policy_from_qdrant(q_client: QdrantClient, policy_id: int):
    try:
        print(f"DEBUG: EMBEDDING_SYNC.PY (delete_policy_from_qdrant): Deleting policy {policy_id}")
        logger.info(f"Deleting policy {policy_id} (and its chunks) from Qdrant.")
        q_client.delete(
            collection_name=VECTOR_DB_COLLECTION_POLICIES,
            points_selector=qdrant_models.FilterSelector(filter=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(key="original_policy_id", match=qdrant_models.MatchValue(value=policy_id))
                ]
            ))
        )
        logger.info(f"Successfully deleted policy {policy_id} (and its chunks) from Qdrant.")
    except Exception as e:
        logger.error(f"Error deleting policy {policy_id} from Qdrant: {e}", exc_info=True)
        print(f"DEBUG: EMBEDDING_SYNC.PY (delete_policy_from_qdrant): EXCEPTION for policy {policy_id}: {e}")