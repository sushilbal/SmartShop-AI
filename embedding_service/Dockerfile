# SmartShop-AI/embedding_service/Dockerfile

# --- Stage 1: The "builder" stage ---
# We use this temporary stage to download the correct, Linux-compatible wheels
FROM python:3.11-slim-bookworm as builder

WORKDIR /app

# Upgrade pip
RUN python -m pip install --upgrade pip

# Download wheels with added retries and a longer timeout to handle network instability
RUN python -m pip download \
    --dest /app/wheels \
    --timeout=100 \
    --retries=5 \
    torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cpu


# --- Stage 2: The "final" stage ---
# This is our actual, clean application image
FROM python:3.11-slim-bookworm

WORKDIR /app

# Upgrade pip
RUN python -m pip install --upgrade pip

# Copy the pre-downloaded wheels from the "builder" stage
COPY --from=builder /app/wheels /app/wheels

# Install PyTorch from the local, compatible wheels
RUN python -m pip install \
    --no-cache-dir \
    --no-index \
    --find-links=/app/wheels \
    torch torchvision torchaudio

# Install the rest of the smaller dependencies
RUN python -m pip install \
    --no-cache-dir \
    sentence-transformers \
    fastapi \
    uvicorn \
    "transformers>=4.30.0" \
    pydantic \
    python-dotenv \
    qdrant-client

# --- The rest of the file is the same ---

ARG MODEL_CACHE_FOLDER_ARG=/app/model_cache

ENV HF_HOME=${MODEL_CACHE_FOLDER_ARG}
ENV TRANSFORMERS_CACHE=${MODEL_CACHE_FOLDER_ARG}

RUN mkdir -p ${HF_HOME} && chmod -R 777 ${HF_HOME}

COPY ./embedding_service/main.py /app/main.py

EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]