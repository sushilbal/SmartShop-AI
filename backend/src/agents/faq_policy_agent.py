from typing import List, TypedDict, Annotated, Sequence, Optional
import operator
import httpx

import json
from langgraph.graph import StateGraph, END

from src.llm_handler import get_llm_response # Changed from get_llm_rag_response
from src.dependencies import get_qdrant_db_client # To get a Qdrant client instance
from config.config import (
    VECTOR_DB_COLLECTION_POLICIES,
    EMBEDDING_SERVICE_URL 
)

# --- Agent State Definition ---
class FaqPolicyAgentState(TypedDict):
    original_query: str
    rewritten_query: str
    query_embedding: List[float]
    retrieved_documents: List[dict] 
    context_for_llm: str
    llm_answer: Optional[str] # Can be None if LLM fails
    chat_history: List[dict] # To store conversation messages [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    final_response: dict 

# --- Node Functions ---
async def rewrite_query_node_faq(state: FaqPolicyAgentState):
    print("--- FAQ/Policy Agent: Rewriting Query for Context ---")
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

async def embed_query_node(state: FaqPolicyAgentState): # Changed to async
    print("--- Node: Embedding Query ---")
    query = state["rewritten_query"]
    
    async with httpx.AsyncClient() as client:
        try:
            
            response = await client.post(EMBEDDING_SERVICE_URL, json={"texts": [query]})
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
            result = response.json()
            

            if "embeddings" in result and isinstance(result["embeddings"], list) and len(result["embeddings"]) > 0:
                embedding = result["embeddings"][0]
                if isinstance(embedding, list):
                    return {"query_embedding": embedding}
            
            print(f"Error: Unexpected response format from embedding service: {result}")
            return {"query_embedding": [], "retrieved_documents": [], "context_for_llm": "Error embedding query due to unexpected response format.", "llm_answer": None}

        except httpx.RequestError as e:
            print(f"Error calling embedding service: {e}")
            return {"query_embedding": [], "retrieved_documents": [], "context_for_llm": f"Error embedding query: {e}", "llm_answer": None}
        except Exception as e:
            print(f"An unexpected error occurred during query embedding: {e}")
            return {"query_embedding": [], "retrieved_documents": [], "context_for_llm": "Error embedding query.", "llm_answer": None}

def search_qdrant_node(state: FaqPolicyAgentState):
    print("--- Node: Searching Qdrant ---")
    query_embedding = state["query_embedding"]
    if not query_embedding:
        return {"retrieved_documents": [], "context_for_llm": "Skipping Qdrant search due to embedding error."}

    q_client = get_qdrant_db_client() 
                                     
    if not q_client:
        return {"retrieved_documents": [], "context_for_llm": "Qdrant client not available."}

    documents = []
    
    try:
        hits = q_client.search(
            collection_name=VECTOR_DB_COLLECTION_POLICIES, # Focus on policies for FAQ
            query_vector=query_embedding,
            limit=15, # Fetch more to filter from
            with_payload=True
        )

        unique_policies = {}
        for hit in hits:
            if hit.payload:
                
                policy_id = hit.payload.get("original_policy_id")
                if policy_id and policy_id not in unique_policies:
                    unique_policies[policy_id] = {
                        "id": hit.id,
                        "score": hit.score,
                        "payload": hit.payload
                    }
        # Limit to the top 5 unique policies
        documents = list(unique_policies.values())[:5]
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

async def call_llm_node(state: FaqPolicyAgentState): 
    print("--- Node: Calling LLM ---")
    query = state["rewritten_query"] 
    context = state["context_for_llm"]
    current_chat_history = state.get("chat_history", []) 

    # Construct the RAG prompt for the current turn
    rag_prompt_content = f"""Based on the following context, please answer the user's question.
If the context doesn't directly answer the question, please state that you couldn't find specific information in the provided documents.

Context:
{context}

User Question: {query}

Answer:"""

    
    prompt_messages = current_chat_history + [
        {"role": "system", "content": "You are a helpful assistant for an e-commerce store, providing concise and relevant answers based on store policies and FAQs."},
        {"role": "user", "content": rag_prompt_content}
    ]

    answer = await get_llm_response(prompt_messages)

    # Update chat history
    updated_history = current_chat_history + [
        {"role": "user", "content": state["original_query"]}, # Save original query to history
        {"role": "assistant", "content": answer if answer else "Sorry, I could not generate a response."}
    ]

    return {"llm_answer": answer, "chat_history": updated_history}

def format_final_response_node(state: FaqPolicyAgentState):
    print("--- Node: Formatting Final Response ---")
    
    final_response_data = {
        "query_type": "semantic_search_rag_langgraph", # New query type
        "llm_answer": state.get("llm_answer"),
        "direct_product_result": None,
        "results": [
            {
                "score": doc.get("score"), 
                "source_collection": VECTOR_DB_COLLECTION_POLICIES, 
                "payload": doc.get("payload"),
                "retrieved_item": None 
            } for doc in state.get("retrieved_documents", [])
        ]
    }
    return {"final_response": final_response_data}


# --- Graph Definition ---
def create_faq_policy_graph():
    workflow = StateGraph(FaqPolicyAgentState)

    workflow.add_node("rewrite_query", rewrite_query_node_faq)
    workflow.add_node("embed_query", embed_query_node)
    workflow.add_node("search_qdrant", search_qdrant_node)
    workflow.add_node("format_context", format_context_node)
    workflow.add_node("call_llm", call_llm_node) 
    workflow.add_node("format_final_response", format_final_response_node)

    workflow.set_entry_point("rewrite_query")
    workflow.add_edge("rewrite_query", "embed_query")
    workflow.add_edge("embed_query", "search_qdrant")
    workflow.add_edge("search_qdrant", "format_context")
    workflow.add_edge("format_context", "call_llm")
    workflow.add_edge("call_llm", "format_final_response")
    workflow.add_edge("format_final_response", END)

    app_graph = workflow.compile()
    return app_graph
