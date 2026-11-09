# WebLens Container for Google Cloud Run and Production MCP Deployment
FROM python:3.11-slim

# Prevent python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/weblens/src:/app/src:/app \
    PORT=8080 \
    WEBLENS_HTTP_HOST=0.0.0.0 \
    WEBLENS_HTTP_PORT=8080 \
    WEBLENS_MCP_PROFILE=full \
    WEBLENS_CACHE_DIR=/tmp/weblens

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy configuration and manifests
COPY README.md pyproject.toml /app/
COPY weblens/ /app/weblens/
COPY src/ /app/src/
COPY *.py /app/

# Install weblens and root package with all dependencies
RUN pip install --no-cache-dir ./weblens .

# Run as an unprivileged user. The cache must be writable by that user.
RUN useradd --create-home --uid 10001 weblens \
    && mkdir -p /tmp/weblens \
    && chown -R weblens:weblens /app /tmp/weblens
USER weblens

# Expose Cloud Run / HTTP port
EXPOSE 8080

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/ || exit 1

# Run WebLens in Streamable HTTP MCP mode, dynamically reading $PORT assigned by Cloud Run.
# Run the canonical WebLens MCP server (weblens package), not the legacy root app.
# The deployed revision before this change was also the weblens package; the
# root server.py is the older MyWebEngine demo and must not silently replace it.
#
# Authentication is mandatory for a non-loopback listener. Set
# WEBLENS_HTTP_TOKEN (from Secret Manager in production) before deploying; the
# process exits with status 2 if the token is missing instead of exposing an
# unauthenticated public endpoint. Do not add --allow-insecure here: it disables
# the token requirement and exposes every tool to the internet.
CMD ["sh", "-c", "exec python -m weblens.cli serve --http --host 0.0.0.0 --port ${PORT:-8080} --profile full"]
