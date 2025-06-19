from typing import List, TypedDict, Optional # Optional is already here, but good to double check all agent files
import httpx

from langgraph.graph import StateGraph, END

from src.llm_handler import get_llm_response
from src.dependencies import get_qdrant_db_client
from config.config import (
    VECTOR_DB_COLLECTION_REVIEWS,
    EMBEDDING_SERVICE_URL
)
from src.models import SearchResultItem

# --- Agent State Definition ---
class ReviewSearchAgentState(TypedDict):
    original_query: str
    query_embedding: List[float]
    retrieved_reviews: List[dict] # List of Qdrant hit payloads for reviews
    context_for_llm: str
    llm_answer: Optional[str]
    chat_history: List[dict] # To store conversation messages
    final_response: dict # To match SearchResponse Pydantic model structure

# --- Node Functions ---
async def embed_query_node_review(state: ReviewSearchAgentState):
    print("--- Review Agent: Embedding Query ---")
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
            return {"query_embedding": [], "retrieved_reviews": [], "context_for_llm": "Error embedding query due to unexpected response format.", "llm_answer": None, "chat_history": state.get("chat_history", [])}

        except httpx.RequestError as e:
            print(f"Error calling embedding service for Review Agent: {e}")
            return {"query_embedding": [], "retrieved_reviews": [], "context_for_llm": f"Error embedding query: {e}", "llm_answer": None, "chat_history": state.get("chat_history", [])}
        except Exception as e:
            print(f"An unexpected error occurred during review query embedding: {e}")
            return {"query_embedding": [], "retrieved_reviews": [], "context_for_llm": "Error embedding query.", "llm_answer": None, "chat_history": state.get("chat_history", [])}

def search_qdrant_reviews_node(state: ReviewSearchAgentState):
    print("--- Review Agent: Searching Qdrant for Reviews ---")
    query_embedding = state["query_embedding"]
    if not query_embedding:
        return {"retrieved_reviews": [], "context_for_llm": "Skipping Qdrant review search due to embedding error."}

    q_client = get_qdrant_db_client()
    if not q_client:
        return {"retrieved_reviews": [], "context_for_llm": "Qdrant client not available for review search."}

    reviews = []
    try:
        hits = q_client.search(
            collection_name=VECTOR_DB_COLLECTION_REVIEWS,
            query_vector=query_embedding,
            limit=5, # Get top 5 review chunks
            with_payload=True
        )
        for hit in hits:
            if hit.payload:
                reviews.append({
                    "id": hit.id,
                    "score": hit.score,
                    "payload": hit.payload
                })
    except Exception as e:
        print(f"Error searching Qdrant for reviews: {e}")
    return {"retrieved_reviews": reviews}


def format_review_context_node(state: ReviewSearchAgentState):
    print("--- Review Agent: Formatting Review Context ---")
    documents = state["retrieved_reviews"]
    context_chunks = []
    for doc in documents:
        payload = doc.get("payload", {})
        product_id = payload.get("product_id", "N/A")
        rating = payload.get("rating", "N/A")
        
        # --- CHANGE THIS LINE ---
        # Change "review_text" to "source_text_snippet" to match the payload in Qdrant
        review_snippet = payload.get("source_text_snippet", "") # Correct key is "source_text_snippet"
        
        context_chunks.append(f"Review for product {product_id}, Rating: {rating}. Snippet: {review_snippet}")
        
    context_str = "\n\n".join(filter(None, context_chunks))
    if not context_str:
        context_str = "No specific review information found for your query."
    return {"context_for_llm": context_str}

async def call_llm_review_node(state: ReviewSearchAgentState):
    print("--- Review Agent: Calling LLM for Reviews ---")
    query = state["original_query"]
    context = state["context_for_llm"]
    current_chat_history = state.get("chat_history", [])

    rag_prompt_content = f"""Based on the following customer reviews, please answer the user's question.
If the context doesn't directly answer the question, state that you couldn't find specific information in the provided reviews.

Customer Reviews Context:
{context}

User Question: {query}

Answer:"""

    prompt_messages = current_chat_history + [
        {"role": "system", "content": "You are a helpful shopping assistant. Answer questions based on the provided customer review information."},
        {"role": "user", "content": rag_prompt_content}
    ]

    answer = await get_llm_response(prompt_messages)

    updated_history = current_chat_history + [
        {"role": "user", "content": query},
        {"role": "assistant", "content": answer if answer else "Sorry, I could not generate a response based on the reviews."}
    ]
    return {"llm_answer": answer, "chat_history": updated_history}

def format_final_review_response_node(state: ReviewSearchAgentState):
    print("--- Review Agent: Formatting Final Review Response ---")
    final_response_data = {
        "query_type": "review_search_rag_langgraph",
        "llm_answer": state.get("llm_answer"),
        "direct_product_result": None,
        "results": [
            SearchResultItem(
                score=doc.get("score"),
                source_collection=VECTOR_DB_COLLECTION_REVIEWS,
                payload=doc.get("payload")
            ).model_dump() for doc in state.get("retrieved_reviews", [])
        ]
    }
    return {"final_response": final_response_data}

# --- Graph Definition ---
def create_review_search_graph():
    workflow = StateGraph(ReviewSearchAgentState)

    workflow.add_node("embed_query_review", embed_query_node_review)
    workflow.add_node("search_qdrant_reviews", search_qdrant_reviews_node)
    workflow.add_node("format_review_context", format_review_context_node)
    workflow.add_node("call_llm_review", call_llm_review_node)
    workflow.add_node("format_final_review_response", format_final_review_response_node)

    workflow.set_entry_point("embed_query_review")
    workflow.add_edge("embed_query_review", "search_qdrant_reviews")
    workflow.add_edge("search_qdrant_reviews", "format_review_context")
    workflow.add_edge("format_review_context", "call_llm_review")
    workflow.add_edge("call_llm_review", "format_final_review_response")
    workflow.add_edge("format_final_review_response", END)

    app_graph = workflow.compile()
    return app_graph