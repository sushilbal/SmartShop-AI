import psycopg2
import csv
import os
from dotenv import load_dotenv
from psycopg2 import sql # For safe SQL query construction

load_dotenv()

# --- Database Configuration ---
# Set these environment variables or replace with your actual credentials
DB_HOST = os.getenv('POSTGRES_HOST', 'localhost')
DB_PORT = os.getenv('POSTGRES_PORT', '5432')
DB_NAME = os.getenv('POSTGRES_DB', 'smartshop_db') # Replace with your DB name
DB_USER = os.getenv('POSTGRES_USER', 'your_user')    # Replace with your DB user
DB_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'your_password') # Replace with your DB password

# --- CSV File Paths ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Construct the base data path relative to the script's location (../data/raw)
BASE_DATA_PATH = os.path.join(SCRIPT_DIR, '..', 'data', 'raw')
PRODUCTS_CSV_PATH = os.path.join(BASE_DATA_PATH, 'products.csv')
REVIEWS_CSV_PATH = os.path.join(BASE_DATA_PATH, 'reviews.csv')
STORE_POLICIES_CSV_PATH = os.path.join(BASE_DATA_PATH, 'store_policies.csv')


# --- SQL Table Definitions (from init.sql) ---
CREATE_PRODUCTS_TABLE_SQL = """
CREATE TABLE products (
    product_id VARCHAR(20) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    brand VARCHAR(255),
    category VARCHAR(255),
    price DECIMAL NOT NULL,
    description TEXT,
    stock INTEGER,
    rating DECIMAL(2,1),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE
);
"""

CREATE_REVIEWS_TABLE_SQL = """
CREATE TABLE reviews (
    review_id SERIAL PRIMARY KEY,
    product_id VARCHAR(20) REFERENCES products(product_id) ON DELETE CASCADE,
    rating DECIMAL(2,1) NOT NULL,
    text TEXT,
    review_date DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE
);
"""

CREATE_STORE_POLICIES_TABLE_SQL = """
CREATE TABLE store_policies (
    policy_id SERIAL PRIMARY KEY,
    policy_type VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    conditions TEXT,
    timeframe INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE
);
"""

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    return conn

def table_exists(cursor, table_name):
    """Checks if a table exists in the public schema."""
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        );
    """, (table_name,))
    return cursor.fetchone()[0]

def is_table_empty(cursor, table_name):
    """Checks if a table is empty."""
    # Use psycopg2.sql for safe table name formatting
    query = sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table_name))
    cursor.execute(query)
    return cursor.fetchone()[0] == 0

def create_table_if_not_exists(conn, table_name, create_sql):
    """
    Ensures the table is created with the specified schema.
    If the table already exists, it is dropped (with CASCADE) and then recreated.
    If it doesn't exist, it's created.
    """
    with conn.cursor() as cur:
        # If the table exists, we drop it to ensure the schema is fresh and correct.
        if table_exists(cur, table_name):
            print(f"Table '{table_name}' exists. Dropping it to recreate with the latest schema (using CASCADE)...")
            # Use CASCADE to drop dependent objects (like foreign key constraints from 'reviews' table)
            # Using psycopg2.sql.Identifier for safe table name formatting.
            drop_query = sql.SQL("DROP TABLE IF EXISTS {} CASCADE;").format(sql.Identifier(table_name))
            cur.execute(drop_query)
            conn.commit()
        cur.execute(create_sql)
        conn.commit()
        print(f"Table '{table_name}' created successfully.")
def populate_products(conn):
    """Populates the products table from its CSV file if the table is empty."""
    with conn.cursor() as cur:
        if not is_table_empty(cur, 'products'):
            print("Table 'products' is not empty. Skipping population.")
            return

        print(f"Populating 'products' table from {PRODUCTS_CSV_PATH}...")
        with open(PRODUCTS_CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            insert_query = """
                INSERT INTO products (product_id, name, brand, category, price, description, stock, rating)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """
            data_to_insert = []
            for row in reader:
                try:
                    stock = int(row['stock']) if row['stock'] else None
                    rating_str = row.get('rating', '')
                    rating = float(rating_str) if rating_str else None
                    
                    data_to_insert.append((
                        row['id'], row['name'], row.get('brand'), row.get('category'),
                        float(row['price']), row.get('description'), stock, rating
                    ))
                except (ValueError, KeyError) as e:
                    print(f"Skipping row in products.csv due to error: {e} in row: {row}")
                    continue
            
            if data_to_insert:
                cur.executemany(insert_query, data_to_insert)
                conn.commit()
                print(f"Successfully populated 'products' table with {len(data_to_insert)} rows.")

def populate_store_policies(conn):
    """Populates the store_policies table from its CSV file if the table is empty."""
    with conn.cursor() as cur:
        if not is_table_empty(cur, 'store_policies'):
            print("Table 'store_policies' is not empty. Skipping population.")
            return

        print(f"Populating 'store_policies' table from {STORE_POLICIES_CSV_PATH}...")
        with open(STORE_POLICIES_CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            insert_query = """
                INSERT INTO store_policies (policy_type, description, conditions, timeframe)
                VALUES (%s, %s, %s, %s);
            """
            data_to_insert = []
            for row in reader:
                try:
                    timeframe = int(row['timeframe']) if row['timeframe'] else None
                    data_to_insert.append((
                        row['policy_type'], row['description'],
                        row.get('conditions'), timeframe
                    ))
                except (ValueError, KeyError) as e:
                    print(f"Skipping row in store_policies.csv due to error: {e} in row: {row}")
                    continue
            
            if data_to_insert:
                cur.executemany(insert_query, data_to_insert)
                conn.commit()
                print(f"Successfully populated 'store_policies' table with {len(data_to_insert)} rows.")

def populate_reviews(conn):
    """Populates the reviews table from its CSV file if the table is empty."""
    with conn.cursor() as cur:
        if not is_table_empty(cur, 'reviews'):
            print("Table 'reviews' is not empty. Skipping population.")
            return

        print(f"Populating 'reviews' table from {REVIEWS_CSV_PATH}...")
        with open(REVIEWS_CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            insert_query = """
                INSERT INTO reviews (product_id, rating, text, review_date)
                VALUES (%s, %s, %s, %s);
            """
            data_to_insert = []
            for row in reader:
                try:
                    data_to_insert.append((
                        row['product_id'], float(row['rating']),
                        row.get('text'), row['date']
                    ))
                except (ValueError, KeyError) as e:
                    print(f"Skipping row in reviews.csv due to error: {e} in row: {row}")
                    continue
            
            if data_to_insert:
                cur.executemany(insert_query, data_to_insert)
                conn.commit()
                print(f"Successfully populated 'reviews' table with {len(data_to_insert)} rows.")

def main():
    """Main function to set up database tables and populate them."""
    conn = None
    try:
        conn = get_db_connection()
        print("Successfully connected to the database.")
        
        # Create tables in order of dependencies
        create_table_if_not_exists(conn, 'products', CREATE_PRODUCTS_TABLE_SQL)
        create_table_if_not_exists(conn, 'store_policies', CREATE_STORE_POLICIES_TABLE_SQL)
        create_table_if_not_exists(conn, 'reviews', CREATE_REVIEWS_TABLE_SQL) # Depends on products

        # Populate tables in order of dependencies
        populate_products(conn)
        populate_store_policies(conn)
        populate_reviews(conn) # Depends on products

        print("Database setup and population process completed.")

    except psycopg2.Error as e:
        print(f"Database error: {e}")
    except FileNotFoundError as e:
        print(f"CSV file not found: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")

if __name__ == '__main__':
    main()