# SmartShop AI: AI-Powered E-commerce Search Platform

SmartShop AI is a sophisticated, multi-agent e-commerce platform that leverages Retrieval-Augmented Generation (RAG) for intelligent, conversational product discovery. It uses a vector database and large language models to provide semantic search capabilities far beyond traditional keyword-based systems.

[cite\_start]The entire application is containerized and designed for cloud-native deployment on AWS using Terraform for Infrastructure as Code. [cite: 1, 2]

## High-Level Architecture

The platform is built on a microservices architecture, with separate services for the frontend, backend API, and AI/ML model serving.

### AWS Cloud Architecture

For production, the services are deployed to a scalable, serverless infrastructure on AWS:

  * **Networking**: A custom VPC with public and private subnets ensures a secure and isolated environment. A NAT Gateway allows private services to access the internet for external API calls (e.g., to OpenAI).
  * **Compute**: All application containers run on **AWS ECS with Fargate**, eliminating the need to manage servers.
  * **Load Balancing**: An **Application Load Balancer (ALB)** securely exposes the frontend to the internet and routes internal API traffic based on URL paths (`/api/*`).
  * **Databases**:
      * **AWS RDS for PostgreSQL** serves as the primary relational database.
      * **AWS ElastiCache for Redis** provides a high-speed cache and session store.
      * The **Qdrant Vector Database** runs as a dedicated service on ECS.
  * **Service Discovery**: **AWS Cloud Map** provides a private DNS namespace (`smartshop.local`) allowing services to discover each other reliably within the VPC.
  * **Container Registry**: **Amazon ECR** stores the Docker images for all services.

## Core Features & Capabilities

  * **Semantic Search**: Users can search for products using natural language questions (e.g., "what do people say about headphones for running?"). [cite\_start]The system understands the *intent* behind the query, not just keywords. [cite: 1, 21, 30]
  * **Multi-Agent System**: A sophisticated router agent analyzes the user's query and directs it to the appropriate specialized agent for handling:
      * [cite\_start]**Product Search Agent**: For semantic searches across product catalogs. [cite: 13]
      * **Review Search Agent**: For questions related to customer opinions and feedback.
      * **FAQ & Policy Agent**: For handling queries about store policies like shipping and returns.
  * [cite\_start]**Retrieval-Augmented Generation (RAG)**: The system retrieves relevant product data, reviews, or policies from the vector database and feeds them to an OpenAI LLM to generate a coherent, context-aware answer. [cite: 15]
  * **Conversational Memory**: The application maintains chat history for each user session using Redis, allowing for contextual follow-up questions.
  * **Infrastructure as Code (IaC)**: The entire cloud infrastructure is defined declaratively using Terraform, enabling automated, repeatable, and version-controlled deployments.

## Tech Stack

| Category | Technology |
| --- |--- |
| **Backend** | Python, FastAPI, SQLAlchemy, Pydantic |
| **Frontend**| React, Vite, Nginx (as web server) |
| **AI / ML**| LangGraph (Multi-Agent Workflows), OpenAI (LLM), Sentence-Transformers (Embeddings), PyTorch |
| **Databases** | AWS RDS (PostgreSQL), AWS ElastiCache (Redis), Qdrant (Vector Database) |
| **Infrastructure & DevOps**| AWS, Terraform, Docker, Docker Compose, Amazon ECR, ECS Fargate |

## Project Structure

```
SmartShop-AI/
├── backend/                # FastAPI backend application (API, agents, business logic)
├── config/                 # Global Python configuration files
├── data/                   # Raw CSV data for initial database population
├── database/               # SQL schema and Dockerfile for the db_init service
├── embedding_service/      # FastAPI service for generating text embeddings
├── frontend/               # React frontend application
├── scripts/                # Python scripts for database population
├── smartshop-iac/          # Terraform Infrastructure as Code for AWS deployment
├── .env                    # Local environment variables
└── docker-compose.yml      # Docker Compose configuration for local development
```

## Execution Guide

There are two primary ways to run this application: locally for development and deployed to the cloud for production.

### Local Development using Docker Compose

This method is ideal for development and testing.

1.  **Prerequisites**: Docker and Docker Compose must be installed.
2.  **Configuration**: Create a `.env` file in the project root with the necessary variables (e.g., `POSTGRES_USER`, `POSTGRES_PASSWORD`, `OPENAI_API_KEY`).
3.  **Build and Run**: From the project root, run:
    ```bash
    docker-compose up --build -d
    ```
4.  **Database Initialization**: The `db_init` service runs automatically to create the schema and populate the databases from the CSV files. Monitor its progress with `docker-compose logs -f db_init`.
5.  **Access Services**:
      * **Frontend UI**: `http://localhost`
      * **Backend API Docs**: `http://localhost:8000/docs`
      * **Qdrant Dashboard**: `http://localhost:6333/dashboard`

### Cloud Deployment to AWS with Terraform

This is the production-grade deployment path.

1.  **Prerequisites**:
      * An AWS account.
      * AWS CLI installed and configured (`aws configure`).
      * Terraform installed.
2.  **IAM Permissions**: Ensure your AWS user has sufficient permissions to create all the necessary resources (EC2, VPC, ECS, RDS, ElastiCache, ECR, IAM, CloudWatch, Cloud Map).
3.  **Deploy Infrastructure**:
      * Navigate to the `smartshop-iac/` directory.
      * Create a `terraform.tfvars` file to store your database credentials.
      * Run the following commands:
        ```bash
        terraform init
        terraform apply
        ```
4.  **Build and Push Docker Images**:
      * Authenticate Docker with your AWS ECR registry (`aws ecr get-login-password...`).
      * For each service (`backend`, `frontend`, `embedding_service`, `vector_db`), build the Docker image, tag it with the ECR repository URI, and push it.
5.  **Initialize the Database**:
      * Run the `db_init` task as a one-time ECS task to populate your RDS and Qdrant databases. This requires running an AWS CLI command (`aws ecs run-task`) to manually trigger the task in your VPC's private subnets.