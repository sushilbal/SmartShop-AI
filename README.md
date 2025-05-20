# SmartShop-AI

SmartShop-AI is a comprehensive e-commerce platform enhanced with AI capabilities, including semantic search powered by text embeddings and a vector database. This project is containerized using Docker and orchestrated with Docker Compose.

## Table of Contents

- [Project Overview](#project-overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Getting Started](#getting-started)
  - [Building and Running the Application](#building-and-running-the-application)
  - [Database Initialization](#database-initialization)
- [Accessing Services](#accessing-services)
- [Stopping the Application](#stopping-the-application)
- [Development Notes](#development-notes)

## Project Overview

This project aims to provide a modern e-commerce experience with intelligent features. It includes a backend API for managing products, reviews, and policies, an embedding service for generating text embeddings, a vector database for storing and searching these embeddings, and a frontend for user interaction.

## Features

*   Relational database for structured data (Products, Reviews, Store Policies).
*   Vector database for storing text embeddings.
*   Dedicated embedding service to generate embeddings.
*   FastAPI backend for robust and fast API development.
*   Automated database schema creation and initial data population.
*   Containerized services for easy setup and deployment.

## Tech Stack

*   **Backend**: Python, FastAPI, SQLAlchemy
*   **Database**: PostgreSQL (Relational), Qdrant (Vector)
*   **Embedding Service**: Python, FastAPI, Sentence-Transformers
*   **Frontend**: (To be specified - e.g., React, Vue, Angular, or static HTML/CSS/JS)
*   **Orchestration**: Docker, Docker Compose

## Project Structure

```
SmartShop-AI/
├── backend/                # FastAPI backend application (API)
│   ├── src/                # Main source code for the backend
│   ├── Dockerfile
│   └── requirements.txt
├── config/                 # Global configuration files (e.g., config.py, column_mappings.py)
├── data/
│   └── raw/                # CSV files for initial data population
├── database/
│   ├── init.sql            # SQL schema definition
│   └── Dockerfile_init     # Dockerfile for the db_init service
├── embedding_service/      # FastAPI service for generating embeddings
│   ├── main.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/               # Frontend application
│   └── Dockerfile
├── scripts/                # Python scripts (e.g., populate_db.py)
│   └── requirements.txt
├── .env                    # Environment variables (create this file)
├── docker-compose.yml      # Docker Compose configuration
└── README.md               # This file
```

## Prerequisites

*   [Docker](https://docs.docker.com/get-docker/)
*   [Docker Compose](https://docs.docker.com/compose/install/)

## Configuration

The application uses a `.env` file in the project root (`/home/sushil/d-codebase/ProjectUp/SmartShopAI/SmartShop-AI/.env`) for configuration. Create this file by copying `.env.example` (if provided) or by creating it manually with the following content, adjusting values as needed:

```env
# PostgreSQL Database Configuration
POSTGRES_USER=myuser
POSTGRES_PASSWORD=mypassword
POSTGRES_DB=smartshop_db

# Embedding Model Configuration
# (Optional, defaults to 'all-MiniLM-L6-v2' if not set in docker-compose.yml or embedding_service/main.py)
EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2

# Qdrant Collection Names (Optional, defaults are set in config/config.py)
# These are used by the populate_db.py script.
# VECTOR_DB_COLLECTION_PRODUCTS=my_custom_products
# VECTOR_DB_COLLECTION_REVIEWS=my_custom_reviews
# VECTOR_DB_COLLECTION_POLICIES=my_custom_policies
```

The `/home/sushil/d-codebase/ProjectUp/SmartShopAI/SmartShop-AI/config/config.py` file loads these environment variables. Critical variables like database credentials and service URLs are expected to be set either in this `.env` file or as system environment variables.

## Getting Started

### Building and Running the Application

1.  Navigate to the project root directory:
    ```bash
    cd /home/sushil/d-codebase/ProjectUp/SmartShopAI/SmartShop-AI/
    ```
2.  Build the Docker images and start all services in detached mode:
    ```bash
    docker-compose up --build -d
    ```
    This command will:
    *   Build Docker images for `backend`, `frontend`, `embedding_model`, and `db_init`.
    *   Pull official images for PostgreSQL (`db`) and Qdrant (`vector_db`).
    *   Create necessary Docker volumes for data persistence.
    *   Start all services in the defined order, respecting dependencies and healthchecks.

### Database Initialization

*   The `db_init` service automatically runs the `/home/sushil/d-codebase/ProjectUp/SmartShopAI/SmartShop-AI/scripts/populate_db.py` script. This occurs after the PostgreSQL database is healthy and the embedding/vector DB services have started.
*   This script:
    1.  Creates the schema in PostgreSQL using `/home/sushil/d-codebase/ProjectUp/SmartShopAI/SmartShop-AI/database/init.sql`.
    2.  Populates PostgreSQL tables from CSV files located in `/home/sushil/d-codebase/ProjectUp/SmartShopAI/SmartShop-AI/data/raw/`.
    3.  Creates collections in Qdrant.
    4.  Fetches data from PostgreSQL, generates embeddings via the `embedding_model` service, and populates the Qdrant vector database.
*   To check the logs of the initialization process:
    ```bash
    docker-compose logs db_init
    ```
    Look for "Database setup and population process completed." The `db_init` container will exit with code 0 upon successful completion.

 your `/home/sushil/d-codebase/ProjectUp/SmartShopAI/SmartShop-AI/.env` file).

3.  **Inspect the data:**
    *   List tables:
        ```sql
        \dt
        ```
        You should see `products`, `reviews`, and `store_policies`.
    *   Check row counts:
        ```sql
        SELECT COUNT(*) FROM products;
        SELECT COUNT(*) FROM reviews;
        SELECT COUNT(*) FROM store_policies;
        ```
    *   View sample data:
        ```sql
        SELECT * FROM products LIMIT 5;
        ```

4.  **Exit `psql` and the container:**
    *   Type `\q` to exit `psql`.
    *   Type `exit` to leave the container shell.

### 2. Validating Vector Database (Qdrant)

Qdrant provides a Web UI and a REST API for inspection.
 
1.  **Using the Qdrant Web UI:**
    *   Open your browser and navigate to `http://localhost:6333/dashboard`.
    *   You should see your collections listed. Based on your `/home/sushil/d-codebase/ProjectUp/SmartShopAI/SmartShop-AI/.env` file, these are `my_custom_products`, `my_custom_reviews`, and `my_custom_policies`.
    *   Click on a collection to see its details, including the number of points (vectors).

2.  **Using `curl` (Command Line):**
    *   List all collections:
        ```bash
        curl http://localhost:6333/collections
        "collections": [
            {
                "name": "policies_collection"
            },
            {
                "name": "products_collection"
            },
            {
                "name": "reviews_collection"
            }
        ]
        ```
    *   Get info about a specific collection (e.g., `my_custom_products`):
        ```bash
        curl http://localhost:6333/collections/products_collection
        ```
        Look for `points_count` in the JSON response.
    *   Scroll through a few points from a collection (e.g., `my_custom_products`):
        ```bash
        curl -X POST -H "Content-Type: application/json" \
             -d '{"limit": 5, "with_payload": true, "with_vectors": false}' \
             http://localhost:6333/collections/products_collection/points/scroll
        ```

If data is missing or counts are incorrect, check the logs of the `db_init` service: `docker-compose logs db_init`.
## Accessing Services

*   **Backend API (FastAPI)**:
    *   Swagger UI (Interactive Docs): `http://localhost:8000/docs`
    *   ReDoc: `http://localhost:8000/redoc`
*   **Frontend Application**:
    *   `http://localhost:80` (or the port your frontend is configured to serve on)
*   **Qdrant Vector Database**:
    *   REST API / Dashboard: `http://localhost:6334/dashboard` (Qdrant's default REST port is 6333, UI is often on 6334)
    *   Client libraries will connect to `vector_db:6333` (gRPC) from within the Docker network.
*   **PostgreSQL Database**:
    *   Connect using a SQL client to:
        *   Host: `localhost`
        *   Port: `5432`
        *   User: Value of `POSTGRES_USER` from your `.env` file.
        *   Password: Value of `POSTGRES_PASSWORD` from your `.env` file.
        *   Database: Value of `POSTGRES_DB` from your `.env` file.
*   **Embedding Service**:
    *   Accessible at `http://localhost:8001`. The primary endpoint is `/embed`.

## Stopping the Application

*   To stop all running services:
    ```bash
    docker-compose down
    ```
*   To stop services and remove named volumes (this will delete persisted data for PostgreSQL and Qdrant):
    ```bash
    docker-compose down -v
    ```

## Development Notes

*   The `backend` service in `docker-compose.yml` mounts the local `./backend` directory into the container at `/app`. This allows for live code reloading during development if your Uvicorn server is started with the `--reload` flag (not currently set in the default `CMD`).
*   Ensure all necessary `__init__.py` files are present in directories intended to be Python packages (e.g., `/home/sushil/d-codebase/ProjectUp/SmartShopAI/SmartShop-AI/config/`, `/home/sushil/d-codebase/ProjectUp/SmartShopAI/SmartShop-AI/backend/src/`).

---

This README should provide a good starting point for anyone working with the SmartShop-AI project.
```