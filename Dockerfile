# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies required for building psycopg2 and other packages
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md ./
COPY findata/ ./findata/

# Install the package with all optional dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ".[all]"

# Expose the port the app runs on
EXPOSE 8000

# Run the FastAPI server via Uvicorn
CMD ["uvicorn", "findata.server.app:app", "--host", "0.0.0.0", "--port", "8000"]
