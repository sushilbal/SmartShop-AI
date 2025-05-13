import os
from dotenv import load_dotenv

load_dotenv()

# --- Project Root Configuration ---
# Assumes this config.py file is in <PROJECT_ROOT>/config/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- Database Configuration ---
DB_HOST = os.getenv('POSTGRES_HOST', 'localhost')
DB_PORT = int(os.getenv('POSTGRES_PORT', '5432'))
DB_NAME = os.getenv('POSTGRES_DB', 'smartshop_db')
DB_USER = os.getenv('POSTGRES_USER', 'myuser')
DB_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'mypassword')

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# --- File Path Configurations ---
BASE_DATA_PATH = os.path.join(PROJECT_ROOT, 'data', 'raw')
PRODUCTS_CSV_PATH = os.path.join(BASE_DATA_PATH, 'products.csv')
REVIEWS_CSV_PATH = os.path.join(BASE_DATA_PATH, 'reviews.csv')
STORE_POLICIES_CSV_PATH = os.path.join(BASE_DATA_PATH, 'store_policies.csv')

INIT_SQL_PATH = os.path.join(PROJECT_ROOT, 'database', 'init.sql')
