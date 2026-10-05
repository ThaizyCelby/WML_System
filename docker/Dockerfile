# LendFlow Dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd -m -s /bin/bash lendflow

WORKDIR /app

# Install Python dependencies
COPY requirements/ ./requirements/
RUN pip install --no-cache-dir -r requirements/production.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/logs /app/media /app/staticfiles /app/tmp
RUN chown -R lendflow:lendflow /app

# Switch to non-root user
USER lendflow

# Run entrypoint
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]