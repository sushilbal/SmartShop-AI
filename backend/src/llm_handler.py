import logging
from typing import List, Optional

from config.config import OPENAI_API_KEY

# Attempt to import openai and initialize client
try:
    import openai
    if OPENAI_API_KEY:
        # For newer versions of the openai library (>=1.0.0)
        # It's good practice to initialize the client once.
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY) # Use AsyncOpenAI for async calls
        OPENAI_CLIENT_INITIALIZED = True
        MODEL_TO_USE = "gpt-3.5-turbo" # Default model
    else:
        client = None
        OPENAI_CLIENT_INITIALIZED = False
        MODEL_TO_USE = None
except ImportError:
    openai = None # So that type hints don't break if library is missing
    client = None
    OPENAI_CLIENT_INITIALIZED = False
    MODEL_TO_USE = None

logger = logging.getLogger(__name__)

if not OPENAI_CLIENT_INITIALIZED:
    logger.warning(
        "OpenAI client could not be initialized. "
        "Ensure the 'openai' library is installed and OPENAI_API_KEY is set in your .env file. "
        "LLM features will be disabled."
    )

async def get_llm_rag_response(query: str, context_chunks: List[str], model: Optional[str] = None) -> Optional[str]:
    """
    Generates a response from an LLM using retrieved context (RAG).
    """
    if not OPENAI_CLIENT_INITIALIZED or client is None:
        logger.error("OpenAI client not initialized. Cannot generate LLM response.")
        return "LLM service is not configured or available."

    selected_model = model if model else MODEL_TO_USE
    if not selected_model: # Should not happen if OPENAI_CLIENT_INITIALIZED is True
        logger.error("No OpenAI model specified or configured.")
        return "LLM model not specified."

    context_text = "\n\n".join(context_chunks) if context_chunks else "No specific context found in our documents for your query."

    prompt = f"""Based on the following context, please answer the user's question.
If the context doesn't directly answer the question, please state that you couldn't find specific information in the provided documents.

Context:
{context_text}

User Question: {query}

Answer:"""

    try:
        logger.info(f"Sending prompt to OpenAI model {selected_model} for query: '{query[:50]}...'")
        response = await client.chat.completions.create(
            model=selected_model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant for an e-commerce store, providing concise and relevant answers."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3 # Adjust for more factual/less creative responses
        )
        answer = response.choices[0].message.content.strip()
        logger.info(f"Received LLM response for query: '{query[:50]}...'")
        return answer
    except openai.APIError as e: # More specific error handling for OpenAI API errors
        logger.error(f"OpenAI API Error: {e.status_code} - {e.message}", exc_info=True)
        return f"Sorry, I encountered an API error (status: {e.status_code}) trying to generate an answer."
    except Exception as e:
        logger.error(f"Unexpected error calling OpenAI API: {e}", exc_info=True)
        return "Sorry, I encountered an unexpected error trying to generate an answer."