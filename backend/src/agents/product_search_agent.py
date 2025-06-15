from typing import List, TypedDict, Optional # Optional is already here, but good to double check all agent files
import httpx

from langgraph.graph import StateGraph, END

from src.llm_handler import get_llm_response # Changed from get_llm_rag_response
from src.dependencies import get_qdrant_db_client
from config.config import (
    VECTOR_DB_COLLECTION_PRODUCTS,
    EMBEDDING_SERVICE_URL
)
from src.models import SearchResultItem # For structuring results

# --- Agent State Definition ---
class ProductSearchAgentState(TypedDict):
    original_query: str
    query_embedding: List[float]
    retrieved_products: List[dict] # List of Qdrant hit payloads for products
    context_for_llm: str
    llm_answer: Optional[str] # LLM answer might be optional for direct product searches
    chat_history: List[dict] # To store conversation messages
    final_response: dict # To match SearchResponse Pydantic model structure

# --- Node Functions ---
async def embed_query_node_product(state: ProductSearchAgentState):
    print("--- Product Agent: Embedding Query ---")
    query = state["original_query"]
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(EMBEDDING_SERVICE_URL, json={"texts": [query]})
            response.raise_for_status()
            result = response.json()
            
            if "embeddings" in result and isinstance(result["embeddings"], list) and len(result["embeddings"]) > 0:
                embedding = result["embeddings"][0]
                if isinstance(embedding, list):
                    return {"query_embedding": embedding}
            
            print(f"Error: Unexpected response format from embedding service: {result}")
            # Ensure all required keys in the state are set even on error to avoid KeyErrors downstream
            return {"query_embedding": [], "retrieved_products": [], "context_for_llm": "Error embedding query due to unexpected response format.", "llm_answer": None, "chat_history": state.get("chat_history", [])}

        except httpx.RequestError as e:
            print(f"Error calling embedding service for Product Agent: {e}")
            return {"query_embedding": [], "retrieved_products": [], "context_for_llm": f"Error embedding query: {e}", "llm_answer": None, "chat_history": state.get("chat_history", [])}
        except Exception as e:
            print(f"An unexpected error occurred during product query embedding: {e}")
            return {"query_embedding": [], "retrieved_products": [], "context_for_llm": "Error embedding query.", "llm_answer": None, "chat_history": state.get("chat_history", [])}

def search_qdrant_products_node(state: ProductSearchAgentState):
    print("--- Product Agent: Searching Qdrant for Products ---")
    query_embedding = state["query_embedding"]
    if not query_embedding:
        return {"retrieved_products": [], "context_for_llm": "Skipping Qdrant product search due to embedding error."}

    q_client = get_qdrant_db_client()
    if not q_client:
        return {"retrieved_products": [], "context_for_llm": "Qdrant client not available for product search."}

    products = []
    try:
        hits = q_client.search(
            collection_name=VECTOR_DB_COLLECTION_PRODUCTS,
            query_vector=query_embedding,
            limit=5, # Get top 5 products
            with_payload=True
        )
        for hit in hits:
            if hit.payload:
                products.append({
                    "id": hit.id,
                    "score": hit.score,
                    "payload": hit.payload
                })
    except Exception as e:
        print(f"Error searching Qdrant for products: {e}")
    return {"retrieved_products": products}

def format_product_context_node(state: ProductSearchAgentState):
    print("--- Product Agent: Formatting Product Context ---")
    documents = state["retrieved_products"]
    context_chunks = []
    for doc in documents:
        payload = doc.get("payload", {})
        name = payload.get("name", "N/A")
        brand = payload.get("brand", "N/A")
        category = payload.get("category", "N/A")
        description_snippet = payload.get("source_text_snippet", "") # Assuming this is the embedded text
        context_chunks.append(f"Product: {name}, Brand: {brand}, Category: {category}. Details: {description_snippet}")
    
    context_str = "\n\n".join(filter(None, context_chunks))
    if not context_str:
        context_str = "No specific product information found for your query."
    return {"context_for_llm": context_str}

async def call_llm_product_node(state: ProductSearchAgentState):
    print("--- Product Agent: Calling LLM for Products ---")
    query = state["original_query"]
    context = state["context_for_llm"]
    current_chat_history = state.get("chat_history", [])

    rag_prompt_content = f"""Based on the following product information, please answer the user's question.
If the context doesn't directly answer the question, state that you couldn't find specific information in the provided product details.

Product Information Context:
{context}

User Question: {query}

Answer:"""

    prompt_messages = current_chat_history + [
        {"role": "system", "content": "You are a helpful shopping assistant. Answer questions based on the provided product information."},
        {"role": "user", "content": rag_prompt_content}
    ]

    answer = await get_llm_response(prompt_messages)

    updated_history = current_chat_history + [
        {"role": "user", "content": query},
        {"role": "assistant", "content": answer if answer else "Sorry, I could not generate a response for your product query."}
    ]
    return {"llm_answer": answer, "chat_history": updated_history}

def format_final_product_response_node(state: ProductSearchAgentState):
    print("--- Product Agent: Formatting Final Product Response ---")
    final_response_data = {
        "query_type": "product_search_rag_langgraph",
        "llm_answer": state.get("llm_answer"),
        "direct_product_result": None, # This agent doesn't do direct ID lookups
        "results": [
            SearchResultItem( # Using the Pydantic model for structure
                score=doc.get("score"),
                source_collection=VECTOR_DB_COLLECTION_PRODUCTS,
                payload=doc.get("payload")
                # retrieved_item could be populated if you fetch full details from PostgreSQL
            ).model_dump() for doc in state.get("retrieved_products", []) # Convert to dict
        ]
    }
    return {"final_response": final_response_data}

# --- Graph Definition ---
def create_product_search_graph():
    workflow = StateGraph(ProductSearchAgentState)

    workflow.add_node("embed_query_product", embed_query_node_product)
    workflow.add_node("search_qdrant_products", search_qdrant_products_node)
    workflow.add_node("format_product_context", format_product_context_node)
    workflow.add_node("call_llm_product", call_llm_product_node)
    workflow.add_node("format_final_product_response", format_final_product_response_node)

    workflow.set_entry_point("embed_query_product")
    workflow.add_edge("embed_query_product", "search_qdrant_products")
    workflow.add_edge("search_qdrant_products", "format_product_context")
    workflow.add_edge("format_product_context", "call_llm_product")
    workflow.add_edge("call_llm_product", "format_final_product_response")
    workflow.add_edge("format_final_product_response", END)

    app_graph = workflow.compile()
    return app_graph