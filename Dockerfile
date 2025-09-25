# Dockerfile for OpenAI Proxy Server
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (entire context for new modules)
COPY . .

# Expose port
EXPOSE 11434

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:11434/v1/models || exit 1

# Run the application (new package structure)
CMD ["python", "-m", "proxy_server.server"]