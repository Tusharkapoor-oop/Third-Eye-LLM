# WebLens Container for Hugging Face Spaces and Production MCP Deployment
FROM python:3.11-slim

# Prevent python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/weblens/src:/app/src:/app \
    PORT=7860 \
    WEBLENS_HTTP_HOST=0.0.0.0 \
    WEBLENS_MCP_PROFILE=full \
    WEBLENS_CACHE_DIR=/tmp/weblens

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces requires running as UID 1000
RUN useradd -m -u 1000 user \
    && mkdir -p /tmp/weblens \
    && chown -R user:user /app /tmp/weblens

# Copy configuration and manifests
COPY README.md pyproject.toml /app/
COPY weblens/ /app/weblens/
COPY src/ /app/src/
COPY *.py /app/

# Install weblens and root package with all dependencies
RUN pip install --no-cache-dir ./weblens . \
    && chown -R user:user /app /tmp/weblens

USER user

# Expose Space / HTTP port (Hugging Face default is 7860)
EXPOSE 7860

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-7860}/healthz || exit 1

# Run WebLens in Streamable HTTP MCP mode, dynamically reading $PORT.
# --allow-insecure enables public binding for the demo Space when no Bearer
# token is configured. When WEBLENS_HTTP_TOKEN is provided via Space secrets,
# token authentication remains fully enforced on /mcp.
CMD ["sh", "-c", "exec python -m weblens.cli serve --http --host 0.0.0.0 --port ${PORT:-7860} --profile full --allow-insecure"]
