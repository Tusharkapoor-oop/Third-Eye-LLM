# WebLens Container for Hugging Face Spaces and Production MCP Deployment
FROM python:3.11-slim

# Prevent python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/weblens/src \
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

# Copy only the active package and root manifest
COPY README.md pyproject.toml /app/
COPY weblens/pyproject.toml weblens/README.md /app/weblens/
COPY weblens/src /app/weblens/src


# Install weblens and root package with only the runtime extras needed.
# Avoid browser/hybrid/redis extras: they pull chromium, ~500MB of ML wheels,
# and Redis clients that are never used by the HTTP MCP profile.
RUN pip install --no-cache-dir --no-compile ./weblens . \
    && chown -R user:user /app /tmp/weblens \
    && find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

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
