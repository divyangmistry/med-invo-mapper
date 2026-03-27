FROM python:3.11-slim

LABEL maintainer="med-invo-mapper"
LABEL description="Medical Invoice & Label Extraction Agent"

# System libs needed by OpenCV (headless) and Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    v4l-utils \
    tesseract-ocr \
    libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (Docker layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent source
COPY . .

# Runtime directories (also created by Config.ensure_dirs(), but good to have here)
RUN mkdir -p /app/outputs /app/db /app/inputs/processed /app/logs

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["python", "main.py"]
