import psycopg2
import csv
import os
import logging # Import the logging module
from psycopg2 import sql # For safe SQL query construction
from config.config import (
    DATABASE_URL,
    PRODUCTS_CSV_PATH,
    REVIEWS_CSV_PATH,
    STORE_POLICIES_CSV_PATH,
    INIT_SQL_PATH
)

from config.column_mappings import (
    PRODUCTS_COLUMN_MAP,
    REVIEWS_COLUMN_MAP,
    STORE_POLICIES_COLUMN_MAP
)

# --- Logger Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_db_connection():
    """Establishes a connection to the PostgreSQL database using DATABASE_URL from config."""
    conn = psycopg2.connect(DATABASE_URL)
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

def execute_sql_from_file(conn, filepath):
    """Executes an SQL script from a file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        sql_script = f.read()
    with conn.cursor() as cur:
        cur.execute(sql_script)
    conn.commit()
    logger.info(f"Successfully executed SQL script: {filepath}")

def _populate_table_from_csv(conn, table_name, csv_path, column_map_details):
    """
    Generic function to populate a table from a CSV file using a defined column map.
    Skips population if the table is not empty.
    """
    with conn.cursor() as cur:
        if not is_table_empty(cur, table_name):
            logger.info(f"Table '{table_name}' is not empty. Skipping population.")
            return

        logger.info(f"Populating '{table_name}' table from {csv_path}...")

        db_columns = [details[1] for details in column_map_details]
        csv_headers = [details[0] for details in column_map_details]
        transform_funcs = [details[2] for details in column_map_details]

        cols_identifiers = sql.SQL(', ').join(map(sql.Identifier, db_columns))
        vals_placeholders = sql.SQL(', ').join([sql.Placeholder()] * len(db_columns))
        insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(table_name),
            cols_identifiers,
            vals_placeholders
        )

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            data_to_insert = []
            for row in reader:
                try:
                    current_row_values = []
                    for i, csv_header in enumerate(csv_headers):
                        raw_value = row.get(csv_header)
                        transform_func = transform_funcs[i]
                        processed_value = transform_func(raw_value) if transform_func else raw_value
                        current_row_values.append(processed_value)
                    data_to_insert.append(tuple(current_row_values))
                except (ValueError, TypeError) as e: # Catch errors from transformation
                    logger.warning(f"Skipping row in {os.path.basename(csv_path)} due to data error: {e} in row: {row}")
                    continue
            
            if data_to_insert:
                cur.executemany(insert_query, data_to_insert)
                conn.commit()
                logger.info(f"Successfully populated '{table_name}' table with {len(data_to_insert)} rows.")

def populate_products(conn):
    """Populates the products table from its CSV file if the table is empty."""
    _populate_table_from_csv(conn, 'products', PRODUCTS_CSV_PATH, PRODUCTS_COLUMN_MAP)

def populate_store_policies(conn):
    """Populates the store_policies table from its CSV file if the table is empty."""
    _populate_table_from_csv(conn, 'store_policies', STORE_POLICIES_CSV_PATH, STORE_POLICIES_COLUMN_MAP)

def populate_reviews(conn):
    """Populates the reviews table from its CSV file if the table is empty."""
    _populate_table_from_csv(conn, 'reviews', REVIEWS_CSV_PATH, REVIEWS_COLUMN_MAP)

def main():
    """Main function to set up database tables and populate them."""
    conn = None
    try:
        conn = get_db_connection()
        logger.info("Successfully connected to the database.")
        
        # Drop existing tables to ensure a fresh schema setup from init.sql
        # Order: drop dependent tables first, or tables that are referenced by others last,
        # or use CASCADE for all. Using CASCADE is generally robust.
        logger.info("Dropping existing tables (if any) to ensure a fresh schema...")
        with conn.cursor() as cur:
            # 'reviews' depends on 'products'
            if table_exists(cur, "reviews"):
                cur.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE;").format(sql.Identifier("reviews")))
                logger.info("Dropped table 'reviews'.")
            
            # 'store_policies' is independent in terms of FKs for this setup
            if table_exists(cur, "store_policies"):
                cur.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE;").format(sql.Identifier("store_policies")))
                logger.info("Dropped table 'store_policies'.")

            # 'products' is referenced by 'reviews'
            if table_exists(cur, "products"):
                cur.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE;").format(sql.Identifier("products")))
                logger.info("Dropped table 'products'.")
            conn.commit()

        logger.info(f"Executing schema creation from {INIT_SQL_PATH}...")
        execute_sql_from_file(conn, INIT_SQL_PATH)
        logger.info("Schema created successfully from init.sql.")
        
        # Populate tables in order of dependencies
        populate_products(conn)
        populate_store_policies(conn)
        populate_reviews(conn) # Depends on products

        logger.info("Database setup and population process completed.")

    except psycopg2.Error as e:
        logger.error(f"Database error: {e}", exc_info=True)
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed.")

if __name__ == '__main__':
    main()