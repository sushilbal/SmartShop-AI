# SmartShop-AI/embedding_service/Dockerfile
FROM python:3.11-slim-bookworm

WORKDIR /app

# Using CPU version of PyTorch for broader compatibility initially
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir sentence-transformers fastapi uvicorn "transformers>=4.30.0" pydantic python-dotenv qdrant-client

# Declare an argument for the model cache folder, with a default value
ARG MODEL_CACHE_FOLDER_ARG=/app/model_cache

# Set Hugging Face cache environment variables.
# These tell the libraries where to download and cache models and other assets.
ENV HF_HOME=${MODEL_CACHE_FOLDER_ARG}
ENV TRANSFORMERS_CACHE=${MODEL_CACHE_FOLDER_ARG}
# Create the cache directory and set permissions
# This ensures the directory exists and is writable by the user inside the container
RUN mkdir -p ${HF_HOME} && chmod -R 777 ${HF_HOME}

COPY ./embedding_service/main.py /app/main.py

EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]