# SmartShop-AI/embedding_service/Dockerfile
FROM python:3.11-slim-bookworm

WORKDIR /app

# Using CPU version of PyTorch for broader compatibility initially
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir sentence-transformers fastapi uvicorn "transformers>=4.30.0" pydantic python-dotenv qdrant-client

COPY ./embedding_service/main.py /app/main.py

EXPOSE 8001
# Using more workers might be beneficial later, but start with 1 for simplicity.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]