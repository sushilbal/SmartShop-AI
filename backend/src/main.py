from fastapi import FastAPI, HTTPException, Depends, Query
from typing import List, Optional, Any
from sqlalchemy.orm import Session
from config.config import (
    DATABASE_URL,
    VECTOR_DB_COLLECTION_PRODUCTS,
    VECTOR_DB_COLLECTION_REVIEWS,
    VECTOR_DB_COLLECTION_POLICIES
)
# from src.database import engine # Import if you need to create tables from main
# from src.models import Base     # Import if you need to create tables from main
# Specific Pydantic models like Product, Review, StorePolicy might be needed later for search responses.
# Create models (ProductCreate, etc.) are now handled in routers.
from src.models import (
    SearchQuery, SearchResponse, SearchResultItem, Product as ProductSchema
)
from datetime import datetime
import logging # For logging Qdrant sync errors
from sqlalchemy.exc import IntegrityError
from src.routers import products, reviews, policies # Import the new routers
from src.dependencies import get_db, get_qdrant_db_client # Import dependencies
from src.embedding_sync import get_embeddings_for_texts
from src.llm_handler import get_llm_rag_response
# Assuming faq_policy_agent.py exists and is set up correctly
from src.agents.faq_policy_agent import create_faq_policy_graph

# --- FastAPI App ---
app = FastAPI()
logger = logging.getLogger(__name__)

# --- LangGraph App Initialization ---
# Compile the graph once on app startup.
faq_policy_agent_graph = None

@app.on_event("startup")
async def startup_event():
    global faq_policy_agent_graph
    try:
        faq_policy_agent_graph = create_faq_policy_graph()
        logger.info("FAQ/Policy LangGraph agent initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize LangGraph agent on startup: {e}", exc_info=True)
        # faq_policy_agent_graph will remain None, endpoint should handle this

# Include the routers
app.include_router(products.router)
app.include_router(reviews.router)
app.include_router(policies.router)

# Optional: If you want to create tables on startup (not recommended for production, use migrations)
# from src.database import engine
# from src.models import Base # Ensure Base is defined in models.py
# Base.metadata.create_all(bind=engine)

# Add this function definition in main.py, likely before the search endpoint
def is_product_id_format(query: str) -> bool:
    """
    Checks if the query string matches a typical product ID format.
    This is a basic heuristic and needs to be adjusted based on your actual product ID patterns.
    Example formats: "TESTPROD001", "SP12345", "ITEM-9876"
    """
    if not query:
        return False
    # Example: Mix of uppercase letters and digits, possibly with a hyphen or specific prefix.
    # This is a very general example. You should make it more specific.
    # For instance, if all your product IDs start with "PROD" followed by numbers:
    import re
    if re.match(r"^[A-Z]{2,4}\d{3,10}$", query): # Example: PROD12345, SP001
        return True
    # For now, a simple check for alphanumeric and length:
    # This part below is a less specific fallback, the regex above is preferred if you have a pattern.
    return query.isalnum() and not query.isnumeric() and len(query) > 4 and len(query) < 20 \
           and any(c.isalpha() for c in query) and any(c.isdigit() for c in query)



# --- Search Endpoint ---
@app.post("/search/", response_model=SearchResponse)
async def search_items(
    search_query: SearchQuery,
    db: Session = Depends(get_db) # q_client might be handled within the agent now
):
    user_query_text = search_query.query
    logger.info(f"Received search query: '{user_query_text}'")

    if is_product_id_format(user_query_text):
        # ... (your existing product ID lookup logic) ...
        # Example:
        from src.models import ProductDB, Product as ProductSchema
        product_db_item = db.query(ProductDB).filter(ProductDB.product_id == user_query_text, ProductDB.is_deleted == False).first()
        if product_db_item:
            return SearchResponse(
                query_type="product_id_lookup",
                direct_product_result=ProductSchema.model_validate(product_db_item),
                results=[],
                llm_answer=f"Displaying details for product ID: {user_query_text}."
            )
        else:
            logger.info(f"No product found with ID '{user_query_text}'. Proceeding with agent-based search.")
    
    # If not a product ID, or direct lookup failed, use the LangGraph agent
    global faq_policy_agent_graph # Use the globally initialized graph
    if faq_policy_agent_graph:
        initial_state = {"original_query": user_query_text}
        # LangGraph's .ainvoke for async execution
        final_state = await faq_policy_agent_graph.ainvoke(initial_state)
        
        # Assuming final_state["final_response"] matches the SearchResponse structure
        # You might need to explicitly construct SearchResponse here
        response_data = final_state.get("final_response", {})
        return SearchResponse(**response_data) # Unpack the dict into the Pydantic model
    else:
        logger.error("FAQ/Policy agent (LangGraph app) not initialized or startup failed.")
        raise HTTPException(status_code=503, detail="Search agent is not available.")
