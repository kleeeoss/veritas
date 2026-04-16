# veritas-sih2025/veritas/ml/model_server/Dockerfile

FROM python:3.10-slim

WORKDIR /app

COPY ./veritas/ml/model_server/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

COPY ./veritas/ml/model_server/server.py /app/server.py

RUN useradd -m -u 10002 veritasml \
    && mkdir -p /app/models \
    && chown -R veritasml:veritasml /app

USER veritasml

EXPOSE 8001
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
