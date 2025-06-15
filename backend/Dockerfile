FROM python:3.11-slim-bookworm

# Install curl for healthchecks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# Using --no-cache-dir to reduce image size
RUN pip install --upgrade pip && pip install --no-cache-dir --upgrade -r requirements.txt

# Copy the rest of the backend application code
# This will copy the contents of host:backend/src/ to container:/app/src/
COPY ./src /app/src

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
# Assumes your FastAPI app instance is named 'app' in 'main.py' inside the 'src' directory
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]