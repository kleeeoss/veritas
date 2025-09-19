# veritas-sih2025/veritas/backend/Dockerfile

FROM python:3.9-slim

# Install Tesseract for OCR, which is a system dependency
RUN apt-get update && apt-get install -y tesseract-ocr

WORKDIR /app

# Copy the backend's specific requirements file
COPY ./veritas/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

# Copy all necessary source code into the container
COPY ./veritas/backend/app /app/app
COPY ./veritas/ml /app/veritas/ml
COPY ./tools /app/tools

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
