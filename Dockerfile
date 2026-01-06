# Multi-stage Dockerfile for PDF Scraper
# Stage 1: Dependencies
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir --user -r requirements.txt \
    && pip install --no-cache-dir --user -r requirements-dev.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash scraper
RUN mkdir -p /app/data /app/config /app/logs && \
    chown -R scraper:scraper /app

# Copy Python packages from builder
COPY --from=builder /root/.local /home/scraper/.local

# Make sure scripts in .local are usable
ENV PATH=/home/scraper/.local/bin:$PATH

# Copy application code
COPY --chown=scraper:scraper . .

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
