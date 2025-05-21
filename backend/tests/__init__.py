import sys
import os
project_root = '/home/sushil/d-codebase/ProjectUp/SmartShopAI/SmartShop-AI/' # Ensure this is your correct absolute project root
if project_root not in sys.path:
    sys.path.insert(0, project_root)

print("--- Python Interactive: Attempting to import config.config ---")
try:
    from config import config
    print("--- Python Interactive: Successfully imported config.config ---")
    # Try accessing the variable
    print(f"Python Interactive: Value of config.EMBEDDING_SERVICE_URL: {hasattr(config, 'EMBEDDING_SERVICE_URL') and config.EMBEDDING_SERVICE_URL}")
except ImportError as e_import:
    print(f"--- Python Interactive: FAILED to import config.config (ImportError) ---")
    print(f"ImportError: {e_import}")
except Exception as e_runtime:
    print(f"--- Python Interactive: FAILED during config.config execution (Other Exception) ---")
    print(f"Exception Type: {type(e_runtime).__name__}")
    print(f"Exception: {e_runtime}")
    # If you want to see the full traceback for the runtime error:
    # import traceback
    # traceback.print_exc()
print("--- Python Interactive: Import attempt finished ---")
