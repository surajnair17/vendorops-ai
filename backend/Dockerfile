FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements*.txt ./
RUN pip install --no-cache-dir -r requirements-cloud.txt
COPY backend backend
RUN useradd --uid 10001 --create-home app && mkdir /data && chown app /data
USER app
ENV VENDOROPS_DATA_DIR=/data
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
