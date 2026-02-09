# Multi-stage Dockerfile for PDF Scraper

# Stage 1: Base dependencies (production runtime deps only)
FROM python:3.11-slim-bookworm as base

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install production Python dependencies
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 1b: Development/Test dependencies (not copied into prod image)
FROM base as dev
COPY requirements-dev.txt constraints.txt ./
RUN pip install --no-cache-dir --user -r requirements-dev.txt

# Stage 2: Runtime (production)
FROM python:3.11-slim-bookworm as runtime

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Upgrade bundled Python packages to fix CVEs in base image
RUN pip install --no-cache-dir --upgrade setuptools wheel

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash scraper
RUN mkdir -p /app/data /app/config /app/logs && \
    chown -R scraper:scraper /app

# Copy Python packages from base (prod-only deps)
COPY --chown=scraper:scraper --from=base /root/.local /home/scraper/.local

# Make sure scripts in .local are usable
ENV PATH=/home/scraper/.local/bin:$PATH

# Copy application code
COPY --chown=scraper:scraper . .

# Image metadata
LABEL org.opencontainers.image.title="pdf-scraper" \
    org.opencontainers.image.description="PDF scraper with RAGFlow integration" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.source="https://github.com/nkissick-del/ragflow_scraper" \
    org.opencontainers.image.version="local"

# Switch to non-root user
USER scraper

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_ENV=production \
    HOST=0.0.0.0 \
    PORT=5000

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# Default command - run the web interface
CMD ["python", "app/main.py"]

# Stage 2b: Runtime with dev/test deps (opt-in for local dev/CI)
FROM runtime as dev-runtime
COPY --chown=scraper:scraper --from=dev /root/.local /home/scraper/.local
