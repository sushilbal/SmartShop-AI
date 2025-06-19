FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Create a non-root user for security
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid 1001 --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy requirements file and install dependencies
COPY requirements.txt .
RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir -r requirements.txt

# Copy the backend source code into the container
COPY ./src /app/src

# Give the appuser ownership of the app directory
RUN chown -R appuser:appgroup /app

# Switch to the non-root user
USER appuser

EXPOSE 8000

# Command to run the backend application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]