# veritas-sih2025/veritas/backend/Dockerfile

FROM python:3.9-slim

# Install OCR dependency and clean cache
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY ./veritas/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

COPY ./veritas/backend/app /app/app
COPY ./veritas/ml /app/veritas/ml
COPY ./tools /app/tools

RUN useradd -m -u 10001 veritas \
    && mkdir -p /app/reviews /app/artifacts \
    && chown -R veritas:veritas /app

USER veritas

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
