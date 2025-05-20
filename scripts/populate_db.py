import psycopg2
import csv
import os
import logging # Import the logging module
from psycopg2 import sql # For safe SQL query construction
from sentence_transformers import SentenceTransformer # For generating embeddings
import uuid # For generating UUIDs for Qdrant point IDs
from qdrant_client import QdrantClient, models # For interacting with Qdrant

from config.config import (
    DATABASE_URL,
    PRODUCTS_CSV_PATH,
    REVIEWS_CSV_PATH,
    STORE_POLICIES_CSV_PATH,
    INIT_SQL_PATH,
    get_embedding_model,        # Import the model loading function
    VECTOR_DB_HOST,             # Qdrant config
    VECTOR_DB_PORT,
    VECTOR_DB_COLLECTION_PRODUCTS,
    VECTOR_DB_COLLECTION_REVIEWS,
    VECTOR_DB_COLLECTION_POLICIES
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
    # Get the embedding model instance from the centralized config function
    model_instance = get_embedding_model()
    embedding_dim = model_instance.get_sentence_embedding_dimension()
    vector_params = models.VectorParams(size=embedding_dim, distance=models.Distance.COSINE)

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
    """Generates embeddings for a list of texts using the local SentenceTransformer model."""
    if not texts:
        return []
    try:
        # Get the embedding model instance from the centralized config function
        model_instance = get_embedding_model()
        embeddings_np = model_instance.encode(texts, show_progress_bar=False)
        return embeddings_np.tolist()
    except Exception as e:
        logger.error(f"Error generating embeddings: {e}", exc_info=True)
        raise # Re-raise the exception

def chunk_text_into_sentences(text: str) -> list[str]:
    """Splits text into sentences using pysbd."""
    # Import pysbd locally or move its initialization if needed globally
    import pysbd
    if not text or not text.strip():
        return []
    try:
        seg = pysbd.Segmenter(language="en", clean=False) # Initialize Segmenter here
        return seg.segment(text)
    except Exception as e: # Keep fallback
        logger.error(f"Error tokenizing text into sentences with pysbd: {e}", exc_info=True)
        return [text] # Fallback to using the whole text as a single chunk

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
    
    logger.info(f"Fetching products from PostgreSQL to populate Qdrant collection '{collection_name}'...")
    all_product_rows = []
    with conn.cursor() as cur:
        # Fetch all necessary fields for payload and text to be chunked
        cur.execute("""
            SELECT product_id, name, brand, category, price, description, stock, rating, created_at, updated_at, is_deleted
            FROM products WHERE is_deleted = FALSE;
        """)
        all_product_rows = cur.fetchall()

    if not all_product_rows:
        logger.info("No products found in PostgreSQL to embed. Skipping Qdrant population for products.")
        return

    logger.info(f"Found {len(all_product_rows)} products. Chunking, embedding, and upserting to Qdrant...")

    # Prepare all chunks and their metadata first
    all_chunks_to_process = [] # Will store tuples of (point_id, text_for_embedding, payload)

    for row in all_product_rows:
        product_id, name, brand, category, price, description, stock, rating, created_at, updated_at, is_deleted = row
        
        # Construct the text for embedding by combining specified fields
        embedding_parts = []
        if name and name.strip():
            embedding_parts.append(name.strip())
        if brand and brand.strip():
            embedding_parts.append(f"Brand: {brand.strip()}")
        if category and category.strip():
            embedding_parts.append(f"Category: {category.strip()}")
        if description and description.strip():
            embedding_parts.append(description.strip())
        
        text_to_chunk = ". ".join(filter(None, embedding_parts))
        
        chunks = chunk_text_into_sentences(text_to_chunk)
        if not chunks: # If no text to chunk (e.g., product with no name/desc), skip
            logger.debug(f"Product {product_id} has no text to chunk. Skipping.")
            continue

        for chunk_idx, chunk_text in enumerate(chunks):
            # point_id = f"{product_id}_chunk_{chunk_idx}" # Old string ID
            point_id = str(uuid.uuid4()) # New UUID for each chunk
            payload = {
                "original_product_id": product_id, # Link back to the parent product
                "name": name,
                "brand": brand,
                "category": category,
                "price": float(price) if price is not None else None,
                "stock": stock,
                "rating": float(rating) if rating is not None else None,
                "chunk_text": chunk_text, # Store the actual chunk text
                "chunk_index": chunk_idx,
                "created_at": created_at.isoformat() if created_at else None,
                "updated_at": updated_at.isoformat() if updated_at else None,
                "is_deleted": is_deleted
            }
            all_chunks_to_process.append((point_id, chunk_text, payload))

    if not all_chunks_to_process:
        logger.info("No text chunks generated from products. Skipping Qdrant population for products.")
        return

    logger.info(f"Generated {len(all_chunks_to_process)} text chunks from products.")

    # Batch process for embedding and upserting
    embedding_batch_size = 64 # How many texts to send to embedding service at once
    points_to_upsert = []

    for i in range(0, len(all_chunks_to_process), embedding_batch_size):
        batch_of_chunks = all_chunks_to_process[i : i + embedding_batch_size]
        
        current_point_ids = [item[0] for item in batch_of_chunks]
        current_texts_to_embed = [item[1] for item in batch_of_chunks]
        current_payloads = [item[2] for item in batch_of_chunks]

        try:
            batch_embeddings = get_embeddings(current_texts_to_embed)

            for j, point_id_val in enumerate(current_point_ids):
                points_to_upsert.append(
                    models.PointStruct(
                        id=point_id_val, # e.g., "SP0001_chunk_0"
                        vector=batch_embeddings[j],
                        payload=current_payloads[j]
                    )
                )
            
            # Upsert this batch of points
            if points_to_upsert:
                qdrant_client.upsert(
                    collection_name=collection_name,
                    wait=True, # Wait for the operation to complete
                    points=points_to_upsert
                )
                logger.info(f"Upserted batch of {len(points_to_upsert)} product chunks to '{collection_name}'.")
                points_to_upsert = [] # Clear batch

        except Exception as e:
            logger.error(f"Error processing embedding/upsert batch for product chunks (starting index {i}): {e}", exc_info=True)
            points_to_upsert = [] # Clear batch to avoid trying to upsert problematic points again
            continue

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
    all_review_rows = []
    with conn.cursor() as cur:
        # Fetch all necessary fields for payload and text to be chunked
        cur.execute("""
            SELECT review_id, product_id, rating, text, review_date, created_at, updated_at, is_deleted
            FROM reviews WHERE is_deleted = FALSE;
        """)
        all_review_rows = cur.fetchall()

    if not all_review_rows:
        logger.info("No reviews found in PostgreSQL to embed. Skipping Qdrant population for reviews.")
        return

    logger.info(f"Found {len(all_review_rows)} reviews. Chunking, embedding, and upserting to Qdrant...")

    all_chunks_to_process = [] # Will store tuples of (point_id, text_for_embedding, payload)

    for row in all_review_rows:
        review_id, product_id, rating, text, review_date, created_at, updated_at, is_deleted = row
        
        text_to_chunk = text if text else ""
        chunks = chunk_text_into_sentences(text_to_chunk)
        if not chunks:
            logger.debug(f"Review {review_id} has no text to chunk. Skipping.")
            continue

        for chunk_idx, chunk_text in enumerate(chunks):
            # point_id = f"{review_id}_chunk_{chunk_idx}" # Old string ID
            point_id = str(uuid.uuid4()) # New UUID for each chunk
            payload = {
                "original_review_id": review_id,
                "product_id": product_id,
                "rating": float(rating) if rating is not None else None,
                "chunk_text": chunk_text,
                "chunk_index": chunk_idx,
                "review_date": review_date.isoformat() if review_date else None,
                "created_at": created_at.isoformat() if created_at else None,
                "updated_at": updated_at.isoformat() if updated_at else None,
                "is_deleted": is_deleted
            }
            all_chunks_to_process.append((point_id, chunk_text, payload))

    if not all_chunks_to_process:
        logger.info("No text chunks generated from reviews. Skipping Qdrant population for reviews.")
        return

    logger.info(f"Generated {len(all_chunks_to_process)} text chunks from reviews.")

    embedding_batch_size = 64
    points_to_upsert = []

    for i in range(0, len(all_chunks_to_process), embedding_batch_size):
        batch_of_chunks = all_chunks_to_process[i : i + embedding_batch_size]

        current_point_ids = [item[0] for item in batch_of_chunks]
        current_texts_to_embed = [item[1] for item in batch_of_chunks]
        current_payloads = [item[2] for item in batch_of_chunks]

        try:
            batch_embeddings = get_embeddings(current_texts_to_embed)

            for j, point_id_val in enumerate(current_point_ids):
                points_to_upsert.append(
                    models.PointStruct(
                        id=point_id_val, # e.g., "123_chunk_0"
                        vector=batch_embeddings[j],
                        payload=current_payloads[j]
                    )
                )
            
            if points_to_upsert:
                qdrant_client.upsert(
                    collection_name=collection_name,
                    wait=True,
                    points=points_to_upsert
                )
                logger.info(f"Upserted batch of {len(points_to_upsert)} review chunks to '{collection_name}'.")
                points_to_upsert = [] # Clear batch

        except Exception as e:
            logger.error(f"Error processing embedding/upsert batch for review chunks (starting index {i}): {e}", exc_info=True)
            points_to_upsert = [] # Clear batch
            continue

def populate_qdrant_policies(conn, qdrant_client):
    """Fetches store policies from PostgreSQL, gets embeddings, and populates Qdrant policies collection."""
    collection_name = VECTOR_DB_COLLECTION_POLICIES
    
    logger.info(f"Fetching store policies from PostgreSQL to populate Qdrant collection '{collection_name}'...")
    all_policy_rows = []
    with conn.cursor() as cur:
        # Fetch all necessary fields for payload and text to be chunked
        cur.execute("""
            SELECT policy_id, policy_type, description, conditions, timeframe, created_at, updated_at, is_deleted
            FROM store_policies WHERE is_deleted = FALSE;
        """)
        all_policy_rows = cur.fetchall()

    if not all_policy_rows:
        logger.info("No store policies found in PostgreSQL to embed. Skipping Qdrant population for policies.")
        return

    logger.info(f"Found {len(all_policy_rows)} store policies. Chunking, embedding, and upserting to Qdrant...")

    all_chunks_to_process = [] # Will store tuples of (point_id, text_for_embedding, payload)

    for row in all_policy_rows:
        policy_id, policy_type, description, conditions, timeframe, created_at, updated_at, is_deleted = row
        
        # Construct the text for embedding
        embedding_parts = []
        if policy_type and policy_type.strip():
            embedding_parts.append(f"Policy Type: {policy_type.strip()}")
        if description and description.strip():
            embedding_parts.append(description.strip())
        # Optionally, include conditions if they are textual and relevant for semantic search
        # if conditions and conditions.strip():
        #     embedding_parts.append(f"Conditions: {conditions.strip()}")
            
        text_to_chunk = ". ".join(filter(None, embedding_parts))
        
        chunks = chunk_text_into_sentences(text_to_chunk)
        if not chunks:
            logger.debug(f"Policy {policy_id} has no text to chunk. Skipping.")
            continue

        for chunk_idx, chunk_text in enumerate(chunks):
            # point_id = f"{policy_id}_chunk_{chunk_idx}" # Old string ID
            point_id = str(uuid.uuid4()) # New UUID for each chunk
            payload = {
                "original_policy_id": policy_id,
                "policy_type": policy_type,
                "conditions": conditions, # Store original conditions text
                "timeframe": timeframe,
                "chunk_text": chunk_text,
                "chunk_index": chunk_idx,
                "created_at": created_at.isoformat() if created_at else None,
                "updated_at": updated_at.isoformat() if updated_at else None,
                "is_deleted": is_deleted
            }
            all_chunks_to_process.append((point_id, chunk_text, payload))

    if not all_chunks_to_process:
        logger.info("No text chunks generated from store policies. Skipping Qdrant population for policies.")
        return

    logger.info(f"Generated {len(all_chunks_to_process)} text chunks from store policies.")

    embedding_batch_size = 64
    points_to_upsert = []

    for i in range(0, len(all_chunks_to_process), embedding_batch_size):
        batch_of_chunks = all_chunks_to_process[i : i + embedding_batch_size]
        current_point_ids = [item[0] for item in batch_of_chunks]
        current_texts_to_embed = [item[1] for item in batch_of_chunks]
        current_payloads = [item[2] for item in batch_of_chunks]

        try:
            batch_embeddings = get_embeddings(current_texts_to_embed)
            for j, point_id_val in enumerate(current_point_ids):
                points_to_upsert.append(
                    models.PointStruct(id=point_id_val, vector=batch_embeddings[j], payload=current_payloads[j])
                )
            if points_to_upsert:
                qdrant_client.upsert(collection_name=collection_name, wait=True, points=points_to_upsert)
                logger.info(f"Upserted batch of {len(points_to_upsert)} policy chunks to '{collection_name}'.")
                points_to_upsert = []
        except Exception as e:
            logger.error(f"Error processing embedding/upsert batch for policy chunks (starting index {i}): {e}", exc_info=True)
            points_to_upsert = []
            continue


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
        populate_qdrant_policies(conn, qdrant_client)

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