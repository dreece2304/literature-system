# Literature Database Service Docker Image
# Multi-stage build for optimized production image

# Build stage
FROM python:3.11-slim as builder

# Install system dependencies for building Python packages
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim as production

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create app user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder stage
COPY --from=builder /root/.local /home/appuser/.local

# Make sure scripts in .local are usable
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy application code
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY config/ ./config/
COPY run_service.py .
COPY .env .

# Copy shared types from monorepo context (if available)
# This will be handled by the docker-compose context
COPY shared/ ./shared/ 2>/dev/null || echo "Shared types will be mounted at runtime"

# Create necessary directories
RUN mkdir -p data/metadata \
    data/pdfs \
    data/cache/search_index \
    logs \
    && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Set Python path to include src directory
ENV PYTHONPATH=/app/src:/app:$PYTHONPATH

# Environment variables with defaults
ENV SERVICE_HOST=0.0.0.0
ENV SERVICE_PORT=8001
ENV SERVICE_NAME=literature-database
ENV DATABASE_URL=sqlite:///data/metadata/literature.db
ENV LOG_LEVEL=INFO
ENV LOG_FILE=logs/litdb.log

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${SERVICE_PORT}/health || exit 1

# Expose the service port
EXPOSE ${SERVICE_PORT}

# Default command
CMD ["python", "run_service.py"]

# Development stage (for docker-compose override)
FROM production as development

# Switch back to root to install development tools
USER root

# Install development dependencies
RUN pip install --no-cache-dir \
    pytest \
    pytest-cov \
    ipython \
    jupyter \
    black \
    pylint

# Copy test files for development
COPY tests/ ./tests/
COPY pytest.ini .
COPY run_tests.py .

# Create volume mount points for development
VOLUME ["/app/data", "/app/logs", "/app/shared"]

# Switch back to app user
USER appuser

# Development environment variables
ENV DEBUG=true
ENV LOG_LEVEL=DEBUG
ENV RELOAD=true

# Development command with auto-reload
CMD ["python", "run_service.py", "--reload", "--log-level", "debug"]