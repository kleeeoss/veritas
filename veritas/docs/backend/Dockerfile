# Start from an official, lightweight Python base image. 'slim' is smaller than the default tag.
FROM python:3.10-slim

# Install system-level dependencies required for our project.
# Tesseract OCR is the key dependency here.
# 'apt-get update' refreshes the list of available packages.
# 'apt-get install -y' installs packages without prompting for confirmation.
# 'tesseract-ocr' is the OCR engine.
# 'build-essential' is needed for some Python packages that compile from source.
# We clean up the apt cache afterwards ('rm -rf ...') to keep the final image size small.
RUN apt-get update && apt-get install -y tesseract-ocr build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container to /app.
# All subsequent commands (COPY, RUN, CMD) will be executed from this directory.
WORKDIR /app

# Copy the Python requirements file into the container.
# We copy this file *first* and install dependencies in a separate step.
# This leverages Docker's layer caching. If the requirements.txt file doesn't change,
# Docker will reuse the existing layer, speeding up future builds significantly.
COPY requirements.txt .

# Install the Python dependencies specified in requirements.txt.
# '--no-cache-dir' disables the pip cache, which helps keep the image size down.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire 'app' directory from your project into the container's /app directory.
# Since WORKDIR is /app, this copies './app' to '/app/app'.
COPY ./app /app/app

# The command that will be executed when a container is started from this image.
# 'uvicorn' is the ASGI server used to run the FastAPI application.
# 'app.main:app' points to the 'app' object inside the 'main.py' file within the 'app' module.
# '--host 0.0.0.0' makes the server accessible from outside the container. This is essential.
# '--port 8000' exposes the application on port 8000 inside the container.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]