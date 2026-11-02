# WebLens Container for Google Cloud Run
FROM python:3.11-slim

# Prevent python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/weblens/src:/app/src \
    PORT=8080 \
    WEBLENS_HTTP_HOST=0.0.0.0 \
    WEBLENS_HTTP_PORT=8080 \
    WEBLENS_MCP_PROFILE=full

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject, README, and source files
COPY README.md pyproject.toml /app/
COPY weblens/ /app/weblens/
COPY src/ /app/src/

# Install weblens and root package with all dependencies
RUN pip install --no-cache-dir ./weblens .

# Expose Cloud Run port
EXPOSE 8080

# Run WebLens in HTTP MCP mode, dynamically reading $PORT assigned by Cloud Run
CMD ["sh", "-c", "python -m weblens.cli serve --http --host 0.0.0.0 --port ${PORT:-8080} --profile full --allow-insecure"]
