# Use the official Python 3.11 image
FROM python:3.12-slim
 
# Set working directory
WORKDIR /app

# Install system dependencies required by OpenCV, media handling, and Krisp build
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends --allow-downgrades \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install uv, a fast Python package installer
RUN pip install --no-cache-dir uv
 
# Copy the full app
COPY . .

# Install dependencies
RUN uv pip install --no-cache-dir --system .
 
# Expose port
EXPOSE 8000
 
# Command to run the app
# Set PYTHONPATH to include src directory so imports work correctly
# CMD ["sh", "-c", "cd /app && PYTHONPATH=/app/src uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
