# veritas-sih2025/veritas/ml/model_server/Dockerfile

FROM python:3.10-slim

WORKDIR /app

# Copy the model server's specific requirements file
COPY ./veritas/ml/model_server/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

# Copy only the server's Python script
COPY ./veritas/ml/model_server/server.py /app/server.py

EXPOSE 8001

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
