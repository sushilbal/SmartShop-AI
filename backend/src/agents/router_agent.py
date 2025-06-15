from typing import List, TypedDict, Optional # Optional is already here, but good to double check all agent files
from langgraph.graph import StateGraph, END
from src.llm_handler import get_llm_classification_response # Use the new classification function
import logging

logger = logging.getLogger(__name__)

# --- Agent State Definition ---
class RouterAgentState(TypedDict):
    original_query: str
    chosen_agent_name: Optional[str] # e.g., "product_search", "review_search", "faq_policy"
    error_message: Optional[str]

# --- Node Functions ---
async def route_query_node(state: RouterAgentState):
    print("--- Router Agent: Classifying Query ---")
    query = state["original_query"]

    # Define the capabilities of each agent for the LLM
    agent_descriptions = """
    Available agents:
    - 'product_search': Use for queries about specific products, product features, comparisons, availability, or general product information.
    - 'review_search': Use for queries asking for user opinions, ratings, feedback, or reviews about products.
    - 'faq_policy': Use for queries about store policies (returns, shipping, privacy), frequently asked questions, customer service, or general store information.

    Analyze the user query below. Which of the listed agents is the most appropriate to handle this query?
    Your response MUST be exactly one of the following agent names: 'product_search', 'review_search', or 'faq_policy'.
    If unsure, respond with 'product_search' as a default.
    """

    prompt_messages = [
        {"role": "system", "content": agent_descriptions},
        {"role": "user", "content": f"User Query: {query}"}
    ]

    chosen_agent = await get_llm_classification_response(prompt_messages)

    # Clean up potential LLM verbosity, e.g., if it says "The best agent is 'product_search'."
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

# Example of how you might test this router agent independently (optional)
# if __name__ == "__main__":
#     import asyncio
#     router_app = create_router_agent_graph()
#     async def run_test():
#         result = await router_app.ainvoke({"original_query": "What is your return policy?"})
#         print(result)
#         result = await router_app.ainvoke({"original_query": "Tell me about the new iPhone model"})
#         print(result)
#         result = await router_app.ainvoke({"original_query": "Are there any good reviews for the Sony headphones?"})
#         print(result)
#     asyncio.run(run_test())