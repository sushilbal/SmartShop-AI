import logging
from typing import List, Optional
from config.config import OPENAI_DEFAULT_MODEL # Import from config
from config.config import OPENAI_API_KEY

# Attempt to import openai and initialize client
try:
    import openai
    if OPENAI_API_KEY:
        # For newer versions of the openai library (>=1.0.0)
        # It's good practice to initialize the client once.
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY) # Use AsyncOpenAI for async calls
        OPENAI_CLIENT_INITIALIZED = True
        # MODEL_TO_USE is now OPENAI_DEFAULT_MODEL from config
    else:
        client = None
        OPENAI_CLIENT_INITIALIZED = False
        # OPENAI_DEFAULT_MODEL would be None if not set
except ImportError:
    openai = None # So that type hints don't break if library is missing
    client = None
    OPENAI_CLIENT_INITIALIZED = False

logger = logging.getLogger(__name__)

if not OPENAI_CLIENT_INITIALIZED:
    logger.warning(
        "OpenAI client could not be initialized. "
        "Ensure the 'openai' library is installed and OPENAI_API_KEY is set in your .env file. "
        "LLM features will be disabled."
    )

async def get_llm_response(
    prompt_messages: List[dict], # Expects a list of messages like [{"role": "system", ...}, {"role": "user", ...}]
    model: Optional[str] = None,
    temperature: float = 0.3 # Default temperature
) -> Optional[str]:
    """
    Generates a response from an LLM based on a list of prompt messages.
    """
    if not OPENAI_CLIENT_INITIALIZED or client is None:
        logger.error("OpenAI client not initialized. Cannot generate LLM response.")
        return "LLM service is not configured or available."

    selected_model = model if model else OPENAI_DEFAULT_MODEL # Use config default
    if not selected_model: # Should not happen if OPENAI_CLIENT_INITIALIZED is True
        logger.error("No OpenAI model specified or configured.")
        return "LLM model not specified."

    try:
        # Log the last user message for brevity if history is long
        log_query_snippet = prompt_messages[-1]['content'][:70] if prompt_messages and prompt_messages[-1]['role'] == 'user' else "N/A"
        logger.info(f"Sending prompt to OpenAI model {selected_model}. Last user message snippet: '{log_query_snippet}...'")
        
        response = await client.chat.completions.create(
            model=selected_model,
            messages=prompt_messages,
            temperature=temperature
        )
        answer = response.choices[0].message.content.strip()
        logger.info(f"Received LLM response. Snippet: '{answer[:70]}...'")
        return answer
    except openai.APIError as e: # More specific error handling for OpenAI API errors
        logger.error(f"OpenAI API Error: {e.status_code} - {e.message}", exc_info=True)
        return f"Sorry, I encountered an API error (status: {e.status_code}) trying to generate an answer."
    except Exception as e:
        logger.error(f"Unexpected error calling OpenAI API: {e}", exc_info=True)
        return "Sorry, I encountered an unexpected error trying to generate an answer."

async def get_llm_classification_response(
    prompt_messages: List[dict], # Expects a list of messages like [{"role": "system", ...}, {"role": "user", ...}]
    model: Optional[str] = None,
    temperature: float = 0.0 # Lower temperature for more deterministic classification
) -> Optional[str]:
    """
    Gets a classification response from an LLM.
    Responds with the raw text output, expecting the prompt to guide the LLM
    to output a specific class name or identifier.
    """
    if not OPENAI_CLIENT_INITIALIZED or client is None:
        logger.error("OpenAI client not initialized. Cannot generate LLM classification.")
        return None # Or raise an error

    selected_model = model if model else OPENAI_DEFAULT_MODEL # Use config default
    if not selected_model:
        logger.error("No OpenAI model specified or configured for classification.")
        return None

    try:
        logger.info(f"Sending classification prompt to OpenAI model {selected_model}...")
        response = await client.chat.completions.create(
            model=selected_model,
            messages=prompt_messages,
            temperature=temperature
        )
        classification_result = response.choices[0].message.content.strip()
        logger.info(f"Received LLM classification: '{classification_result}'")
        return classification_result
    except Exception as e:
        logger.error(f"Unexpected error calling OpenAI API for classification: {e}", exc_info=True)
        return None