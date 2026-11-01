# Isolated WebLens Evaluation and Security Sandbox Container
FROM python:3.11-slim

# Prevent python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/lab:/lab/weblens/src:/lab/src \
    WEBLENS_CACHE_DIR=/lab/weblens-lab/sandbox/temporary/cache \
    WEBLENS_LOG_LEVEL=INFO

WORKDIR /lab

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject and sources
COPY pyproject.toml README.md /lab/
COPY weblens/ /lab/weblens/
COPY src/ /lab/src/
COPY weblens-lab/ /lab/weblens-lab/

# Install packages
RUN pip install --no-cache-dir ./weblens .

# Default command: run sandbox isolation verification
CMD ["python", "weblens-lab/sandbox/config/isolation.py"]

