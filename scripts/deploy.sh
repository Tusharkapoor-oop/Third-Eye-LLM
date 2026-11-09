#!/usr/bin/env bash
# scripts/deploy.sh
# Production deployment automation for WebLens MCP Server

set -euo pipefail

TARGET="${1:-docker}"
IMAGE_NAME="weblens-mcp"
TAG="${2:-latest}"
GCP_REGION="${GCP_REGION:-us-central1}"
GCP_SERVICE="${GCP_SERVICE:-weblens}"

# Authentication is mandatory for a non-loopback listener. Fail fast instead of
# publishing an unauthenticated MCP endpoint (the server also exits with status 2
# if this is missing, but the check here produces a clearer message).
if [ -z "${WEBLENS_HTTP_TOKEN:-}" ]; then
  echo "ERROR: WEBLENS_HTTP_TOKEN must be set (generate one with: openssl rand -hex 32)" >&2
  echo "       In production prefer a secret, e.g. --set-secrets WEBLENS_HTTP_TOKEN=weblens-http-token:latest" >&2
  exit 2
fi

echo "=================================================="
echo " WebLens Production Deployment: Target = $TARGET"
echo "=================================================="

case "$TARGET" in
  docker)
    echo "[1/3] Building Docker container image: $IMAGE_NAME:$TAG..."
    docker build -t "$IMAGE_NAME:$TAG" .

    echo "[2/3] Stopping previous container instances if running..."
    docker stop "$IMAGE_NAME" 2>/dev/null || true
    docker rm "$IMAGE_NAME" 2>/dev/null || true

    echo "[3/3] Launching production container on port 8080..."
    docker run -d \
      --name "$IMAGE_NAME" \
      --restart unless-stopped \
      --security-opt no-new-privileges:true \
      -p 8080:8080 \
      -e PORT=8080 \
      -e WEBLENS_HTTP_HOST=0.0.0.0 \
      -e WEBLENS_HTTP_PORT=8080 \
      -e WEBLENS_MCP_PROFILE=full \
      -e WEBLENS_HTTP_TOKEN="$WEBLENS_HTTP_TOKEN" \
      "$IMAGE_NAME:$TAG"

    echo "WebLens successfully deployed locally on http://localhost:8080/mcp (bearer token required)"
    ;;

  cloudrun)
    echo "[1/2] Building and submitting Cloud Run container..."
    # App-level bearer auth is enforced from WEBLENS_HTTP_TOKEN. For production,
    # prefer --set-secrets instead of --set-env-vars so the token is not stored
    # in plain-text revision config (see README deployment section).
    gcloud run deploy "$GCP_SERVICE" \
      --source . \
      --platform managed \
      --region "$GCP_REGION" \
      --allow-unauthenticated \
      --port 8080 \
      --set-env-vars WEBLENS_HTTP_HOST=0.0.0.0,WEBLENS_HTTP_PORT=8080,WEBLENS_MCP_PROFILE=full,WEBLENS_HTTP_TOKEN="$WEBLENS_HTTP_TOKEN"

    echo "[2/2] Retrieving Cloud Run endpoint URL..."
    SERVICE_URL=$(gcloud run services describe "$GCP_SERVICE" --platform managed --region "$GCP_REGION" --format 'value(status.url)')
    echo "WebLens Cloud Run successfully deployed: $SERVICE_URL/mcp"
    ;;

  compose)
    echo "Starting WebLens via docker-compose..."
    docker-compose up -d --build
    echo "WebLens compose service running."
    ;;

  *)
    echo "Usage: $0 [docker|cloudrun|compose] [tag]"
    exit 1
    ;;
esac

