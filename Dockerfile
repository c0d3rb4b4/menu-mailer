FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/

# Default mount point for menu images
RUN mkdir -p /mnt/menu-images

# Expose HTTP port (health/status only)
EXPOSE 8082

# Run the application
CMD ["python", "-m", "src.app"]
