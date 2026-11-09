# scripts/deploy.ps1
# Production deployment automation for WebLens MCP Server on Windows

param (
    [string]$Target = "docker",
    [string]$Tag = "latest",
    [string]$GcpRegion = "us-central1",
    [string]$GcpService = "weblens"
)

$ErrorActionPreference = "Stop"
$ImageName = "weblens-mcp"

# Authentication is mandatory for a non-loopback listener. Fail fast instead of
# publishing an unauthenticated MCP endpoint (the server also exits with status 2
# if this is missing, but the check here produces a clearer message).
if (-not $env:WEBLENS_HTTP_TOKEN) {
    throw "WEBLENS_HTTP_TOKEN must be set (generate one with: openssl rand -hex 32). In production prefer a secret, e.g. --set-secrets WEBLENS_HTTP_TOKEN=weblens-http-token:latest"
}

Write-Host "=================================================="
Write-Host " WebLens Production Deployment: Target = $Target"
Write-Host "=================================================="

switch ($Target.ToLower()) {
    "docker" {
        Write-Host "[1/3] Building Docker container image: ${ImageName}:${Tag}..."
        docker build -t "$ImageName`:$Tag" .

        Write-Host "[2/3] Stopping previous container instances if running..."
        docker stop $ImageName 2>$null | Out-Null
        docker rm $ImageName 2>$null | Out-Null

        Write-Host "[3/3] Launching production container on port 8080..."
        docker run -d `
            --name $ImageName `
            --restart unless-stopped `
            --security-opt no-new-privileges:true `
            -p 8080:8080 `
            -e PORT=8080 `
            -e WEBLENS_HTTP_HOST=0.0.0.0 `
            -e WEBLENS_HTTP_PORT=8080 `
            -e WEBLENS_MCP_PROFILE=full `
            -e WEBLENS_HTTP_TOKEN=$env:WEBLENS_HTTP_TOKEN `
            "$ImageName`:$Tag"

        Write-Host "WebLens successfully deployed locally on http://localhost:8080/mcp (bearer token required)"
    }

    "cloudrun" {
        Write-Host "[1/2] Building and submitting Cloud Run container..."
        # App-level bearer auth is enforced from WEBLENS_HTTP_TOKEN. For production,
        # prefer --set-secrets instead of --set-env-vars so the token is not stored
        # in plain-text revision config (see README deployment section).
        gcloud run deploy $GcpService `
            --source . `
            --platform managed `
            --region $GcpRegion `
            --allow-unauthenticated `
            --port 8080 `
            --set-env-vars "WEBLENS_HTTP_HOST=0.0.0.0,WEBLENS_HTTP_PORT=8080,WEBLENS_MCP_PROFILE=full,WEBLENS_HTTP_TOKEN=$env:WEBLENS_HTTP_TOKEN"

        Write-Host "[2/2] Retrieving Cloud Run endpoint URL..."
        $serviceUrl = (gcloud run services describe $GcpService --platform managed --region $GcpRegion --format 'value(status.url)')
        Write-Host "WebLens Cloud Run successfully deployed: $serviceUrl/mcp"
    }

    "compose" {
        Write-Host "Starting WebLens via docker-compose..."
        docker compose up -d --build
        Write-Host "WebLens compose service running."
    }

    default {
        Write-Host "Usage: .\scripts\deploy.ps1 -Target [docker|cloudrun|compose] -Tag [tag]"
    }
}

