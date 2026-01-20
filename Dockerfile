FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml ./

# Install uv and Python dependencies
RUN pip install --no-cache-dir uv && \
    uv pip install --system -e .

# Copy application code
COPY src/ ./src/
COPY data/ ./data/
COPY scripts/ ./scripts/

# Create directory for vector DB persistence
RUN mkdir -p /app/data/vector_db

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    LOG_LEVEL=INFO \
    VECTOR_DB_PATH=/app/data/vector_db

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
