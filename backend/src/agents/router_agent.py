from typing import List, TypedDict, Optional 
from langgraph.graph import StateGraph, END
from src.llm_handler import get_llm_classification_response 
import logging

logger = logging.getLogger(__name__)

# --- Agent State Definition ---
class RouterAgentState(TypedDict):
    original_query: str
    chat_history: List[dict]
    chosen_agent_name: Optional[str] 
    error_message: Optional[str]

# --- Node Functions ---
async def route_query_node(state: RouterAgentState):
    print("--- Router Agent: Classifying Query ---")
    query = state["original_query"]
    chat_history = state.get("chat_history", [])

    
    agent_descriptions = """You are an expert at routing a user's query to the correct agent.
    Based on the user's query and the conversation history, determine which of the following agents is most appropriate.

    Available agents:
    - 'product_search': Use for queries about specific products, product features, comparisons, availability, or general product information. This is also a good default if the user is asking a follow-up question about products.
    - 'review_search': Use for queries asking for user opinions, ratings, feedback, or reviews about products.
    - 'faq_policy': Use for queries about store policies (returns, shipping, privacy), frequently asked questions, customer service, or general store information.
   
    Your response MUST be exactly one of the following agent names: 'product_search', 'review_search', or 'faq_policy'.
    """
    
    prompt_messages = chat_history + [
        {"role": "system", "content": agent_descriptions},
        {"role": "user", "content": f"Latest User Query: {query}"}
    ]

    chosen_agent = await get_llm_classification_response(prompt_messages)

    
    cleaned_chosen_agent = None
    if chosen_agent:
        for valid_name in ["product_search", "review_search", "faq_policy"]:
            if valid_name in chosen_agent:
                cleaned_chosen_agent = valid_name
                break

    valid_agents = ["product_search", "review_search", "faq_policy"]
    if cleaned_chosen_agent and cleaned_chosen_agent in valid_agents:
        logger.info(f"Router LLM chose agent: {cleaned_chosen_agent} for query: '{query}' (Original LLM output: '{chosen_agent}')")
        return {"chosen_agent_name": cleaned_chosen_agent, "error_message": None}
    else:
        logger.warning(f"Router LLM returned an invalid or no agent: '{chosen_agent}' (cleaned: '{cleaned_chosen_agent}'). Defaulting to 'product_search'. Query: '{query}'")
        # Fallback or error handling
        return {"chosen_agent_name": "product_search", "error_message": f"Router failed to classify, defaulted. LLM output: {chosen_agent}"}

# --- Graph Definition ---
def create_router_agent_graph():
    workflow = StateGraph(RouterAgentState)

    workflow.add_node("route_query", route_query_node)
    workflow.set_entry_point("route_query")
    
    # The router agent's job is just to classify, so it ends after routing.
    # The actual invocation of the chosen agent will happen in main.py
    # based on the 'chosen_agent_name' from this graph's state.
    workflow.add_edge("route_query", END) 

    app_graph = workflow.compile()
    return app_graph
