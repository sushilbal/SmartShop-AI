import psycopg2
import csv
import os
import logging # Import the logging module
import requests # For making HTTP requests to the embedding service
from psycopg2 import sql # For safe SQL query construction
from qdrant_client import QdrantClient, models # For interacting with Qdrant

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

from config.config import ( # Import Qdrant and Embedding Service config
    EMBEDDING_SERVICE_URL,
    VECTOR_DB_HOST,
    VECTOR_DB_PORT,
    VECTOR_DB_COLLECTION_PRODUCTS,
    VECTOR_DB_COLLECTION_REVIEWS,
    VECTOR_DB_COLLECTION_POLICIES
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

# --- Qdrant Helper Functions ---

def get_qdrant_client():
    """Establishes a connection to the Qdrant vector database."""
    try:
        client = QdrantClient(host=VECTOR_DB_HOST, port=VECTOR_DB_PORT)
        # Optional: Check connection
        client.get_collections()
        logger.info(f"Successfully connected to Qdrant at {VECTOR_DB_HOST}:{VECTOR_DB_PORT}.")
        return client
    except Exception as e:
        logger.error(f"Failed to connect to Qdrant at {VECTOR_DB_HOST}:{VECTOR_DB_PORT}: {e}", exc_info=True)
        raise

def create_qdrant_collections(client):
    """Creates Qdrant collections if they don't already exist."""
    # Define vector parameters (size should match your embedding model output)
    # all-MiniLM-L6-v2 outputs 384-dimensional vectors
    vector_params = models.VectorParams(size=384, distance=models.Distance.COSINE)

    collections_to_create = {
        VECTOR_DB_COLLECTION_PRODUCTS: vector_params,
        VECTOR_DB_COLLECTION_REVIEWS: vector_params,
        VECTOR_DB_COLLECTION_POLICIES: vector_params,
    }

    existing_collections = client.get_collections().collections
    existing_collection_names = {c.name for c in existing_collections}

    for collection_name, params in collections_to_create.items():
        if collection_name not in existing_collection_names:
            logger.info(f"Collection '{collection_name}' not found. Creating...")
            try:
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=params
                )
                logger.info(f"Collection '{collection_name}' created successfully.")
            except Exception as e:
                 logger.error(f"Failed to create collection '{collection_name}': {e}", exc_info=True)
                 # Decide if you want to stop or continue if collection creation fails
                 raise # Re-raise the exception to stop the script
        else:
            logger.info(f"Collection '{collection_name}' already exists. Skipping creation.")

def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Sends text to the embedding service and returns embeddings."""
    try:
        response = requests.post(EMBEDDING_SERVICE_URL, json={"texts": texts})
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        embeddings = response.json().get("embeddings")
        if not embeddings or len(embeddings) != len(texts):
             raise ValueError("Embedding service returned unexpected response format or number of embeddings.")
        return embeddings
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling embedding service at {EMBEDDING_SERVICE_URL}: {e}", exc_info=True)
        raise # Re-raise the exception

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

def populate_qdrant_products(conn, qdrant_client):
    """Fetches products from PostgreSQL, gets embeddings, and populates Qdrant products collection."""
    collection_name = VECTOR_DB_COLLECTION_PRODUCTS
    
    # Check if Qdrant collection is empty (optional, but prevents duplicates if script is re-run)
    # Note: Checking emptiness in Qdrant is different from PostgreSQL.
    # A simple check could be to count points, but that might be slow for large collections.
    # For simplicity here, we'll assume if the script runs, we intend to populate Qdrant.
    # A more robust approach might involve checking if specific product IDs already exist as points.
    
    logger.info(f"Fetching products from PostgreSQL to populate Qdrant collection '{collection_name}'...")
    products_data = []
    with conn.cursor() as cur:
        cur.execute("SELECT product_id, name, description FROM products WHERE is_deleted = FALSE;")
        products_data = cur.fetchall()

    if not products_data:
        logger.info("No products found in PostgreSQL to embed. Skipping Qdrant population for products.")
        return

    logger.info(f"Found {len(products_data)} products to embed. Getting embeddings and upserting to Qdrant...")

    batch_size = 64 # Adjust based on embedding service capacity and memory
    points_to_upsert = []

    for i in range(0, len(products_data), batch_size):
        batch_data = products_data[i:i+batch_size]
        batch_ids = [row[0] for row in batch_data] # product_id
        # Combine name and description for embedding
        batch_texts = [f"{row[1]}. {row[2]}" if row[2] else row[1] for row in batch_data]

        try:
            batch_embeddings = get_embeddings(batch_texts)

            for j, product_id in enumerate(batch_ids):
                # Create payload (metadata) for Qdrant point
                # Include relevant data from PostgreSQL row, excluding the text used for embedding if preferred
                # For simplicity, let's fetch the full row again or pass more data from the initial fetch
                # A better approach would be to fetch all necessary columns initially.
                # Let's refetch the full product data for the payload for now:
                with conn.cursor() as cur_payload:
                     cur_payload.execute("SELECT * FROM products WHERE product_id = %s;", (product_id,))
                     full_product_row = cur_payload.fetchone()
                     # Assuming column order matches init.sql: product_id, name, brand, category, price, description, stock, rating, created_at, updated_at, is_deleted
                     payload = {
                         "product_id": full_product_row[0],
                         "name": full_product_row[1],
                         "brand": full_product_row[2],
                         "category": full_product_row[3],
                         "price": float(full_product_row[4]), # Convert Decimal to float for JSON/Qdrant payload
                         "stock": full_product_row[6],
                         "rating": float(full_product_row[7]) if full_product_row[7] is not None else None,
                         "created_at": full_product_row[8].isoformat() if full_product_row[8] else None,
                         "updated_at": full_product_row[9].isoformat() if full_product_row[9] else None,
                         "is_deleted": full_product_row[10]
                         # Note: description is not included in payload here, but could be if needed
                     }

                points_to_upsert.append(
                    models.PointStruct(
                        id=str(product_id), # Qdrant point IDs are typically integers or UUIDs, but strings are also supported in recent versions. Using string to match VARCHAR product_id.
                        vector=batch_embeddings[j],
                        payload=payload
                    )
                )

            # Upsert the batch
            if points_to_upsert:
                qdrant_client.upsert(
                    collection_name=collection_name,
                    wait=True, # Wait for the operation to complete
                    points=points_to_upsert
                )
                logger.info(f"Upserted batch of {len(points_to_upsert)} products to '{collection_name}'.")
                points_to_upsert = [] # Clear batch

        except Exception as e:
            logger.error(f"Error processing batch {i//batch_size + 1} for products: {e}", exc_info=True)
            # Decide if you want to stop or continue on batch error
            # For now, we'll log and continue, but you might want to raise or handle differently
            points_to_upsert = [] # Clear batch to avoid trying to upsert problematic points again
            continue

    # Upsert any remaining points in the last batch
    if points_to_upsert:
         try:
            qdrant_client.upsert(
                collection_name=collection_name,
                wait=True,
                points=points_to_upsert
            )
            logger.info(f"Upserted final batch of {len(points_to_upsert)} products to '{collection_name}'.")
         except Exception as e:
            logger.error(f"Error processing final batch for products: {e}", exc_info=True)

def populate_store_policies(conn):
    """Populates the store_policies table from its CSV file if the table is empty."""
    _populate_table_from_csv(conn, 'store_policies', STORE_POLICIES_CSV_PATH, STORE_POLICIES_COLUMN_MAP)

def populate_reviews(conn):
    """Populates the reviews table from its CSV file if the table is empty."""
    _populate_table_from_csv(conn, 'reviews', REVIEWS_CSV_PATH, REVIEWS_COLUMN_MAP)

def populate_qdrant_reviews(conn, qdrant_client):
    """Fetches reviews from PostgreSQL, gets embeddings, and populates Qdrant reviews collection."""
    collection_name = VECTOR_DB_COLLECTION_REVIEWS
    
    logger.info(f"Fetching reviews from PostgreSQL to populate Qdrant collection '{collection_name}'...")
    reviews_data = []
    with conn.cursor() as cur:
        # Fetch review_id, product_id, and text
        cur.execute("SELECT review_id, product_id, text FROM reviews WHERE is_deleted = FALSE;")
        reviews_data = cur.fetchall()

    if not reviews_data:
        logger.info("No reviews found in PostgreSQL to embed. Skipping Qdrant population for reviews.")
        return

    logger.info(f"Found {len(reviews_data)} reviews to embed. Getting embeddings and upserting to Qdrant...")

    batch_size = 64 # Adjust based on embedding service capacity and memory
    points_to_upsert = []

    for i in range(0, len(reviews_data), batch_size):
        batch_data = reviews_data[i:i+batch_size]
        batch_ids = [row[0] for row in batch_data] # review_id (SERIAL/int)
        batch_texts = [row[2] if row[2] else "" for row in batch_data] # review text

        # Skip empty texts if your embedding model doesn't handle them well
        valid_batch_ids = [batch_ids[j] for j, text in enumerate(batch_texts) if text.strip()]
        valid_batch_texts = [text for text in batch_texts if text.strip()]
        
        if not valid_batch_texts:
            logger.debug(f"Skipping batch {i//batch_size + 1} for reviews: no valid text found.")
            continue

        try:
            batch_embeddings = get_embeddings(valid_batch_texts)

            valid_batch_data = [batch_data[j] for j, text in enumerate(batch_texts) if text.strip()]

            for j, review_row in enumerate(valid_batch_data):
                # Fetch full review data for payload
                with conn.cursor() as cur_payload:
                     cur_payload.execute("SELECT * FROM reviews WHERE review_id = %s;", (review_row[0],))
                     full_review_row = cur_payload.fetchone()
                     # Assuming column order matches init.sql: review_id, product_id, rating, text, review_date, created_at, updated_at, is_deleted
                     payload = {
                         "review_id": full_review_row[0],
                         "product_id": full_review_row[1],
                         "rating": float(full_review_row[2]),
                         "review_date": full_review_row[4].isoformat() if full_review_row[4] else None,
                         "created_at": full_review_row[5].isoformat() if full_review_row[5] else None,
                         "updated_at": full_review_row[6].isoformat() if full_review_row[6] else None,
                         "is_deleted": full_review_row[7]
                         # Note: text is not included in payload here, but could be
                     }

                points_to_upsert.append(
                    models.PointStruct(
                        id=review_row[0], # Use integer ID directly for SERIAL PK
                        vector=batch_embeddings[j],
                        payload=payload
                    )
                )

            # Upsert the batch
            if points_to_upsert:
                qdrant_client.upsert(
                    collection_name=collection_name,
                    wait=True,
                    points=points_to_upsert
                )
                logger.info(f"Upserted batch of {len(points_to_upsert)} reviews to '{collection_name}'.")
                points_to_upsert = [] # Clear batch

        except Exception as e:
            logger.error(f"Error processing batch {i//batch_size + 1} for reviews: {e}", exc_info=True)
            points_to_upsert = [] # Clear batch
            continue

    # Upsert any remaining points in the last batch
    if points_to_upsert:
         try:
            qdrant_client.upsert(
                collection_name=collection_name,
                wait=True,
                points=points_to_upsert
            )
            logger.info(f"Upserted final batch of {len(points_to_upsert)} reviews to '{collection_name}'.")
         except Exception as e:
            logger.error(f"Error processing final batch for reviews: {e}", exc_info=True)


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
        
        # Populate PostgreSQL tables in order of dependencies
        populate_products(conn)
        populate_store_policies(conn)
        populate_reviews(conn) # Depends on products

        # --- Populate Qdrant Vector DB ---
        qdrant_client = get_qdrant_client()
        create_qdrant_collections(qdrant_client)

        # Populate Qdrant collections (can be done in any order)
        # Fetch data from PostgreSQL, get embeddings, and upsert to Qdrant
        populate_qdrant_products(conn, qdrant_client)
        populate_qdrant_reviews(conn, qdrant_client)
        # populate_qdrant_policies(conn, qdrant_client) # Add this when you have policy text to embed

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