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
import uuid # For generating session IDs
import logging # For logging Qdrant sync errors
from sqlalchemy.exc import IntegrityError
from src.routers import products, reviews, policies # Import the new routers
from src.dependencies import get_db, get_qdrant_db_client # Import dependencies
from src.embedding_sync import get_embeddings_for_texts
from src.llm_handler import get_llm_response # Changed from get_llm_rag_response
from src.agents.faq_policy_agent import create_faq_policy_graph
# Import the new agent graph creators
from src.agents.review_search_agent import create_review_search_graph
from src.agents.product_search_agent import create_product_search_graph
from src.agents.router_agent import create_router_agent_graph # Import the router agent

# --- FastAPI App ---
import redis.asyncio as redis # For aioredis
import json # For serializing chat history
from config.config import REDIS_URL # Import REDIS_URL from your config
app = FastAPI()
logger = logging.getLogger(__name__)

# Define health check endpoint immediately after app initialization
@app.get("/health", status_code=200, include_in_schema=False) # exclude from OpenAPI docs
async def health_check():
    return {"status": "healthy"}

# --- Redis Client Initialization ---
redis_client = None

# --- LangGraph App Initialization ---
# Compile the graph once on app startup.
faq_policy_agent_graph = None # For FAQs and store policies
product_search_agent_graph = None # For product-related semantic searches
review_search_agent_graph = None # For review-related semantic searches
router_agent_graph = None # For routing queries
# Removed: session_memory_store: dict[str, list[dict]] = {}

@app.on_event("startup")
async def startup_event():
    global faq_policy_agent_graph, product_search_agent_graph, review_search_agent_graph, router_agent_graph
    global redis_client # Add redis_client here

    try:
        faq_policy_agent_graph = create_faq_policy_graph()
        logger.info("FAQ/Policy LangGraph agent initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize FAQ/Policy LangGraph agent on startup: {e}", exc_info=True)

    try:
        product_search_agent_graph = create_product_search_graph()
        logger.info("Product Search LangGraph agent initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Product Search LangGraph agent on startup: {e}", exc_info=True)
    try:
        review_search_agent_graph = create_review_search_graph()
        logger.info("Review Search LangGraph agent initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Review Search LangGraph agent on startup: {e}", exc_info=True)
    
    try:
        router_agent_graph = create_router_agent_graph()
        logger.info("Router LangGraph agent initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Router LangGraph agent on startup: {e}", exc_info=True)
    
    # Initialize Redis client
    try:
        redis_client = await redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
        await redis_client.ping() # Test connection
        logger.info(f"Successfully connected to Redis at {REDIS_URL} for session storage.")
    except Exception as e:
        logger.error(f"Failed to connect to Redis at {REDIS_URL}: {e}", exc_info=True)
        redis_client = None # Ensure it's None if connection fails

@app.on_event("shutdown")
async def shutdown_event():
    global redis_client
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed.")

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

    session_id = search_query.session_id
    if not session_id:
        session_id = str(uuid.uuid4())
        logger.info(f"No session_id provided, generated new one: {session_id}")
    
    current_session_history = []
    if redis_client:
        try:
            history_json = await redis_client.get(f"session:{session_id}")
            if history_json:
                current_session_history = json.loads(history_json)
            logger.info(f"Session {session_id} loaded with {len(current_session_history)} previous messages from Redis.")
        except Exception as e:
            logger.error(f"Error fetching history from Redis for session {session_id}: {e}", exc_info=True)
            # Proceed with empty history if Redis fails
    else:
        logger.warning("Redis client not available. Session history will not be persisted for this request.")

    if is_product_id_format(user_query_text):
        # ... (your existing product ID lookup logic) ...
        # Example:
        from src.models import ProductDB, Product as ProductSchema
        product_db_item = db.query(ProductDB).filter(ProductDB.product_id == user_query_text, ProductDB.is_deleted == False).first()
        if product_db_item:
            return SearchResponse(
                session_id_returned=session_id, # Return session_id
                query_type="product_id_lookup",
                direct_product_result=ProductSchema.model_validate(product_db_item),
                results=[],
                llm_answer=f"Displaying details for product ID: {user_query_text}."
            )
        else:
            logger.info(f"No product found with ID '{user_query_text}'. Proceeding with agent-based search.")
    
    # --- Agent Routing ---
    if not router_agent_graph:
        logger.error("Router agent not initialized. Cannot proceed with agent-based search.")
        raise HTTPException(status_code=503, detail="Search routing service is unavailable.")

    try:
        router_initial_state = {
            "original_query": user_query_text,
            "chat_history": current_session_history # Pass the chat history to the router
        }
        router_final_state = await router_agent_graph.ainvoke(router_initial_state)
        chosen_agent_key = router_final_state.get("chosen_agent_name")
        logger.info(f"Router agent chose: '{chosen_agent_key}' for query: '{user_query_text}'")
    except Exception as e:
        logger.error(f"Error invoking router agent: {e}", exc_info=True)
        # Fallback to a default agent or raise error
        chosen_agent_key = "product_search" # Default fallback
        logger.warning(f"Router agent failed, defaulting to '{chosen_agent_key}' for query: '{user_query_text}'")

    # Map the chosen agent key to the actual graph instance
    agent_map = {
        "product_search": (product_search_agent_graph, "Product Search"),
        "review_search": (review_search_agent_graph, "Review Search"),
        "faq_policy": (faq_policy_agent_graph, "FAQ/Policy")
    }

    chosen_agent_graph = None
    agent_name = ""
    if chosen_agent_key in agent_map:
        chosen_agent_graph, agent_name = agent_map[chosen_agent_key]
    else:
        logger.warning(f"Unknown agent key '{chosen_agent_key}' from router. Defaulting to Product Search.")
        chosen_agent_graph, agent_name = agent_map["product_search"] # Default if key is somehow invalid

    if chosen_agent_graph:
        try:
            # Pass the current session's chat history to the chosen agent
            initial_state = {
                "original_query": user_query_text,
                "chat_history": current_session_history # Pass loaded history
            }
            # LangGraph's .ainvoke for async execution
            final_state = await chosen_agent_graph.ainvoke(initial_state)
            
            # Save the updated chat history back to the session store
            updated_session_history = final_state.get("chat_history", [])
            if redis_client:
                try:
                    # Store for 1 hour (3600 seconds), adjust as needed
                    await redis_client.set(f"session:{session_id}", json.dumps(updated_session_history), ex=3600) 
                    logger.info(f"Session {session_id} history updated in Redis with {len(updated_session_history)} messages.")
                except Exception as e:
                    logger.error(f"Error saving history to Redis for session {session_id}: {e}", exc_info=True)
            
            # Assuming final_state["final_response"] matches the SearchResponse structure
            response_data = final_state.get("final_response", {})
            # Ensure query_type is set if the agent didn't set it or set it differently
            if "query_type" not in response_data or not response_data["query_type"]:
                 response_data["query_type"] = f"{agent_name.lower().replace('/', '_').replace(' ', '_')}_rag_langgraph" # Default query_type
            return SearchResponse(**response_data, session_id_returned=session_id) # Unpack and add session_id
        except Exception as e:
            logger.error(f"Error invoking {agent_name} agent: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error processing search with {agent_name} agent.")
    else:
        logger.error(f"{agent_name} agent (LangGraph app) not initialized or startup failed.")
        raise HTTPException(status_code=503, detail=f"{agent_name} search agent is not available.")
