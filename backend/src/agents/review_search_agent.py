from typing import List, TypedDict, Optional 
import httpx
import json

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
    rewritten_query: str
    query_embedding: List[float]
    retrieved_reviews: List[dict] 
    context_for_llm: str
    llm_answer: Optional[str]
    chat_history: List[dict] 
    final_response: dict 

# --- Node Functions ---
async def rewrite_query_node_review(state: ReviewSearchAgentState):
    print("--- Review Agent: Rewriting Query for Context ---")
    original_query = state["original_query"]
    chat_history = state.get("chat_history", [])

    if not chat_history:
        return {"rewritten_query": original_query}

    
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

async def embed_query_node_review(state: ReviewSearchAgentState):
    print("--- Review Agent: Embedding Query ---")
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
            limit=15, # Fetch more to filter from
            with_payload=True
        )
        
        unique_reviews = {}
        for hit in hits:
            if hit.payload:
                review_id = hit.payload.get("original_review_id")
                if review_id and review_id not in unique_reviews:
                    unique_reviews[review_id] = {
                        "id": hit.id,
                        "score": hit.score,
                        "payload": hit.payload
                    }
        
        # Limit to the top 5 unique reviews
        reviews = list(unique_reviews.values())[:5]
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
        
        
        review_snippet = payload.get("text_chunk", "")
        
        context_chunks.append(f"Review for product {product_id}, Rating: {rating}. Snippet: {review_snippet}")
        
    context_str = "\n\n".join(filter(None, context_chunks))
    if not context_str:
        context_str = "No specific review information found for your query."
    return {"context_for_llm": context_str}

async def call_llm_review_node(state: ReviewSearchAgentState):
    print("--- Review Agent: Calling LLM for Reviews ---")
    query = state["rewritten_query"] # Use the rewritten query for context
    context = state["context_for_llm"]
    current_chat_history = state.get("chat_history", [])

   
    rag_prompt_content = f"""You are a helpful shopping assistant. Your task is to answer the user's question based on the provided customer review snippets.
Analyze the reviews and synthesize an answer.

- If the user asks for "pros and cons", "comparison", or "which is best", summarize the positive and negative points from the reviews. Use the ratings as a guide.
- Address the user's question directly.
- If the provided reviews are too generic (e.g., they all say the same thing) or don't contain enough information to answer the question, clearly state that you can only provide a limited summary based on the available feedback. Do not invent information.
- Keep the answer concise and focused on the user's query.

**Customer Reviews Context:**
{context}

**User's Question:** "{query}"

**Helpful Summary of Reviews:**"""

    prompt_messages = current_chat_history + [
        {"role": "system", "content": "You are a helpful shopping assistant that summarizes customer reviews to answer user questions."},
        {"role": "user", "content": rag_prompt_content}
    ]

    answer = await get_llm_response(prompt_messages)

    updated_history = current_chat_history + [
        {"role": "user", "content": state["original_query"]}, # Save original query to history
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

    workflow.add_node("rewrite_query_review", rewrite_query_node_review)
    workflow.add_node("embed_query_review", embed_query_node_review)
    workflow.add_node("search_qdrant_reviews", search_qdrant_reviews_node)
    workflow.add_node("format_review_context", format_review_context_node)
    workflow.add_node("call_llm_review", call_llm_review_node)
    workflow.add_node("format_final_review_response", format_final_review_response_node)

    workflow.set_entry_point("rewrite_query_review")
    workflow.add_edge("rewrite_query_review", "embed_query_review")
    workflow.add_edge("embed_query_review", "search_qdrant_reviews")
    workflow.add_edge("search_qdrant_reviews", "format_review_context")
    workflow.add_edge("format_review_context", "call_llm_review")
    workflow.add_edge("call_llm_review", "format_final_review_response")
    workflow.add_edge("format_final_review_response", END)

    app_graph = workflow.compile()
    return app_graph