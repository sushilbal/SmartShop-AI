from typing import List, TypedDict, Optional
import httpx
import json

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
    rewritten_query: str
    query_embedding: List[float]
    retrieved_products: List[dict] # List of Qdrant hit payloads for products
    context_for_llm: str
    llm_answer: Optional[str] # LLM answer might be optional for direct product searches
    chat_history: List[dict] # To store conversation messages
    final_response: dict # To match SearchResponse Pydantic model structure

# --- Node Functions ---
async def rewrite_query_node_product(state: ProductSearchAgentState):
    print("--- Product Agent: Rewriting Query for Context ---")
    original_query = state["original_query"]
    chat_history = state.get("chat_history", [])

    if not chat_history:
        # If there's no history, the original query is the one to use
        return {"rewritten_query": original_query}

    # A more robust prompt to ensure context is carried over for vector search.
    rewrite_prompt = f"""You are an expert at rephrasing a follow-up question to be a standalone question that is perfect for a vector database search.
Based on the **entire conversation history**, rephrase the follow-up question to be a self-contained, standalone question that includes all necessary context, especially the main subject of the conversation (like a product category or specific product names).

**Conversation History:**
{json.dumps(chat_history, indent=2)}

**Follow-up Question:** "{original_query}"

**Standalone Search Query:**"""

    prompt_messages = [
        {"role": "system", "content": "You are an expert at rephrasing conversational questions into standalone, self-contained search queries."},
        {"role": "user", "content": rewrite_prompt}
    ]

    rewritten_query = await get_llm_response(prompt_messages)
    cleaned_rewritten_query = rewritten_query.strip().strip('"')
    print(f"Original query: '{original_query}'. Rewritten query: '{cleaned_rewritten_query}'")
    return {"rewritten_query": cleaned_rewritten_query if cleaned_rewritten_query else original_query}

async def embed_query_node_product(state: ProductSearchAgentState):
    print("--- Product Agent: Embedding Query ---")
    query = state["rewritten_query"]
    
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
        # Fetch more results to have a better chance of finding unique products after filtering
        hits = q_client.search(
            collection_name=VECTOR_DB_COLLECTION_PRODUCTS,
            query_vector=query_embedding,
            limit=15, # Fetch more to filter from
            with_payload=True
        )
        
        unique_products = {}
        for hit in hits:
            if hit.payload:
                # Assuming 'product_id' is in the payload to identify unique products.
                # The first time we see a product_id, we keep it, as results are ordered by score.
                product_id = hit.payload.get("original_product_id")
                if product_id and product_id not in unique_products:
                    unique_products[product_id] = {
                        "id": hit.id,
                        "score": hit.score,
                        "payload": hit.payload
                    }
        
        # Limit to the top 5 unique products
        products = list(unique_products.values())[:5]
    except Exception as e:
        print(f"Error searching Qdrant for products: {e}")
    return {"retrieved_products": products}

# In backend/src/agents/product_search_agent.py

def format_product_context_node(state: ProductSearchAgentState):
    print("--- Product Agent: Formatting Product Context ---")
    documents = state["retrieved_products"]
    context_chunks = []
    for doc in documents:
        payload = doc.get("payload", {})
        name = payload.get("name", "N/A")
        brand = payload.get("brand", "N/A")
        category = payload.get("category", "N/A")
        # --- CHANGE THIS LINE ---
        # Change source_text_snippet to chunk_text to match what's in Qdrant
        description_snippet = payload.get("chunk_text", "") # Correct key is "chunk_text"
        context_chunks.append(f"Product: {name}, Brand: {brand}, Category: {category}. Details: {description_snippet}")
    
    context_str = "\n\n".join(filter(None, context_chunks))
    if not context_str:
        context_str = "No specific product information found for your query."
    return {"context_for_llm": context_str}

# async def call_llm_product_node(state: ProductSearchAgentState):
#     print("--- Product Agent: Calling LLM for Products ---")
#     query = state["original_query"]
#     context = state["context_for_llm"]
#     current_chat_history = state.get("chat_history", [])

#     rag_prompt_content = f"""Based on the following product information, please answer the user's question.
# If the context doesn't directly answer the question, state that you couldn't find specific information in the provided product details.

# Product Information Context:
# {context}

# User Question: {query}

# Answer:"""

#     prompt_messages = current_chat_history + [
#         {"role": "system", "content": "You are a helpful shopping assistant. Answer questions based on the provided product information."},
#         {"role": "user", "content": rag_prompt_content}
#     ]

#     answer = await get_llm_response(prompt_messages)

#     updated_history = current_chat_history + [
#         {"role": "user", "content": query},
#         {"role": "assistant", "content": answer if answer else "Sorry, I could not generate a response for your product query."}
#     ]
#     return {"llm_answer": answer, "chat_history": updated_history}

# In backend/src/agents/product_search_agent.py

async def call_llm_product_node(state: ProductSearchAgentState):
    print("--- Product Agent: Calling LLM for Products ---")
    query = state["rewritten_query"] # Use the rewritten query for context
    context = state["context_for_llm"]
    current_chat_history = state.get("chat_history", [])

    # --- THIS IS THE CORRECTED, MORE EFFECTIVE PROMPT ---
    rag_prompt_content = f"""You are a helpful e-commerce shopping assistant.
Your goal is to help the user find the products they are looking for based on their request.
Use the "Product Information Context" below, which contains the results of a database search, to help the user.

Summarize the products from the context that are relevant to the user's question.
Present the options clearly. If there are multiple products, you can list them.
If the context is empty or does not contain relevant information, simply state that you couldn't find any specific products matching their request.

Product Information Context:
{context}

User Question: {query}

Helpful Summary:"""

    prompt_messages = current_chat_history + [
        {"role": "system", "content": "You are a helpful shopping assistant designed to summarize and present product options to users."},
        {"role": "user", "content": rag_prompt_content}
    ]

    answer = await get_llm_response(prompt_messages)

    updated_history = current_chat_history + [
        {"role": "user", "content": state["original_query"]}, # Save original query to history
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

    workflow.add_node("rewrite_query_product", rewrite_query_node_product)
    workflow.add_node("embed_query_product", embed_query_node_product)
    workflow.add_node("search_qdrant_products", search_qdrant_products_node)
    workflow.add_node("format_product_context", format_product_context_node)
    workflow.add_node("call_llm_product", call_llm_product_node)
    workflow.add_node("format_final_product_response", format_final_product_response_node)

    workflow.set_entry_point("rewrite_query_product")
    workflow.add_edge("rewrite_query_product", "embed_query_product")
    workflow.add_edge("embed_query_product", "search_qdrant_products")
    workflow.add_edge("search_qdrant_products", "format_product_context")
    workflow.add_edge("format_product_context", "call_llm_product")
    workflow.add_edge("call_llm_product", "format_final_product_response")
    workflow.add_edge("format_final_product_response", END)

    app_graph = workflow.compile()
    return app_graph