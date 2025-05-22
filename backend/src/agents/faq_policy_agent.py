from typing import List, TypedDict, Annotated, Sequence
import operator

# Assuming you'll use LangChain components for Qdrant and OpenAI
# from langchain_community.vectorstores import Qdrant # Example
# from langchain_openai import ChatOpenAI # Example
# from langchain_core.documents import Document # Example

from langgraph.graph import StateGraph, END

# Import your existing helpers (you might refactor them slightly to fit LangGraph nodes)
from src.embedding_sync import get_embeddings_for_texts
from src.llm_handler import get_llm_rag_response # You might adapt this or use LangChain's LLM wrapper
from src.dependencies import get_qdrant_db_client # To get a Qdrant client instance
from config.config import (
    VECTOR_DB_COLLECTION_POLICIES,
    VECTOR_DB_COLLECTION_REVIEWS, # If FAQ can also search reviews
    VECTOR_DB_COLLECTION_PRODUCTS # If FAQ can also search products
)
# You'll need to pass the Qdrant client to the nodes or make it accessible.

# --- Agent State Definition ---
class FaqPolicyAgentState(TypedDict):
    original_query: str
    query_embedding: List[float]
    retrieved_documents: List[dict] # List of Qdrant hit payloads or formatted docs
    context_for_llm: str
    llm_answer: str
    final_response: dict # Could be your SearchResponse Pydantic model structure

# --- Node Functions ---
def embed_query_node(state: FaqPolicyAgentState):
    print("--- Node: Embedding Query ---")
    query = state["original_query"]
    embedding_list = get_embeddings_for_texts([query])
    if not embedding_list or not embedding_list[0]:
        # Handle error: maybe set a flag or raise an exception LangGraph can catch
        print("Error: Could not embed query")
        return {"query_embedding": [], "retrieved_documents": [], "context_for_llm": "Error embedding query."}
    return {"query_embedding": embedding_list[0]}

def search_qdrant_node(state: FaqPolicyAgentState):
    print("--- Node: Searching Qdrant ---")
    query_embedding = state["query_embedding"]
    if not query_embedding:
        return {"retrieved_documents": [], "context_for_llm": "Skipping Qdrant search due to embedding error."}

    q_client = get_qdrant_db_client() # This needs to be managed carefully in async context if client is not thread-safe
                                     # Or pass client instance if graph is compiled per request
    if not q_client:
        return {"retrieved_documents": [], "context_for_llm": "Qdrant client not available."}

    documents = []
    # Simplified search across policies for now
    try:
        hits = q_client.search(
            collection_name=VECTOR_DB_COLLECTION_POLICIES, # Focus on policies for FAQ
            query_vector=query_embedding,
            limit=5, # Get top 5 policy chunks
            with_payload=True
        )
        for hit in hits:
            if hit.payload:
                documents.append({
                    "id": hit.id,
                    "score": hit.score,
                    "payload": hit.payload 
                    # Add other hit attributes if needed, e.g., hit.vector (though usually not needed for context)
                })
    except Exception as e:
        print(f"Error searching Qdrant: {e}")
        # Handle error
    return {"retrieved_documents": documents}

def format_context_node(state: FaqPolicyAgentState):
    print("--- Node: Formatting Context ---")
    documents = state["retrieved_documents"]
    # Now 'documents' is a list of dicts, each containing 'payload'
    context_chunks = [
        doc["payload"].get("chunk_text", "") 
        for doc in documents if doc.get("payload") and doc["payload"].get("chunk_text")
    ]
    context_str = "\n\n".join(filter(None, context_chunks))
    if not context_str:
        context_str = "No specific context found in our documents for your query."
    return {"context_for_llm": context_str}

async def call_llm_node(state: FaqPolicyAgentState): # Make it async if get_llm_rag_response is async
    print("--- Node: Calling LLM ---")
    query = state["original_query"]
    context = state["context_for_llm"]
    # Adapt get_llm_rag_response or use LangChain's ChatOpenAI directly
    # For simplicity, assuming get_llm_rag_response can be used here
    answer = await get_llm_rag_response(query, [context]) # Pass context as a list of one item
    return {"llm_answer": answer}

def format_final_response_node(state: FaqPolicyAgentState):
    print("--- Node: Formatting Final Response ---")
    # This node would construct the final dictionary matching your SearchResponse Pydantic model
    # For example:
    final_response_data = {
        "query_type": "semantic_search_rag_langgraph", # New query type
        "llm_answer": state.get("llm_answer"),
        "direct_product_result": None,
        "results": [ # Reconstruct SearchResultItem-like dicts from retrieved_documents
            {
                "score": doc.get("score"), # Now score is available directly from the stored doc
                "source_collection": VECTOR_DB_COLLECTION_POLICIES, # Example
                "payload": doc.get("payload"),
                "retrieved_item": None # Or fetch from DB if needed
            } for doc in state.get("retrieved_documents", [])
        ]
    }
    return {"final_response": final_response_data}


# --- Graph Definition ---
def create_faq_policy_graph():
    workflow = StateGraph(FaqPolicyAgentState)

    workflow.add_node("embed_query", embed_query_node)
    workflow.add_node("search_qdrant", search_qdrant_node)
    workflow.add_node("format_context", format_context_node)
    workflow.add_node("call_llm", call_llm_node) # Use `await call_llm_node` if using LangChain's .ainvoke
    workflow.add_node("format_final_response", format_final_response_node)

    workflow.set_entry_point("embed_query")
    workflow.add_edge("embed_query", "search_qdrant")
    workflow.add_edge("search_qdrant", "format_context")
    workflow.add_edge("format_context", "call_llm")
    workflow.add_edge("call_llm", "format_final_response")
    workflow.add_edge("format_final_response", END)

    app_graph = workflow.compile()
    return app_graph

# You would typically compile the graph once on app startup
# faq_policy_app = create_faq_policy_graph()
