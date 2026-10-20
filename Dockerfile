# Base image with Python 3.12 Slim (Debian Bookworm)
FROM python:3.12-slim

# Set environment variables for Cloud Run & Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    HEADLESS=true \
    AI_CRAWLER_DATA_DIR=/tmp/ai_crawler_data \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Install system dependencies for OpenCV, PyMuPDF, Tesseract OCR, and Playwright Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgl1 \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-vie \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium && \
    rm -rf /var/lib/apt/lists/*

# Copy Backend application code
COPY ai_crawler ./ai_crawler

# Ensure writable data directory exists
RUN mkdir -p /tmp/ai_crawler_data/exports \
             /tmp/ai_crawler_data/screenshots \
             /tmp/ai_crawler_data/documents \
             /tmp/ai_crawler_data/templates

EXPOSE 8080

# Start FastAPI server with Uvicorn listening on Cloud Run's $PORT
CMD ["sh", "-c", "uvicorn ai_crawler.server:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
