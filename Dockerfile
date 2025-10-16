# Use an official Python runtime as a parent image.
# python:3.9-slim is a good choice for keeping the image size down.
FROM python:3.9-slim

# Set the working directory inside the container.
WORKDIR /app

# Copy the requirements file first to leverage Docker's build cache.
# The dependencies will only be re-installed if requirements.txt changes.
COPY requirements.txt .

# Install the Python dependencies.
# --no-cache-dir ensures that pip does not store the download cache, reducing the image size.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application source code into the container.
COPY . .

# Expose port 8000, which is the default port for the FastAPI application.
# This makes the port available to the host machine.
EXPOSE 8000

# Define the command to run the application when the container starts.
# Uvicorn is used as the ASGI server to run the FastAPI app ('app' from 'api.py').
# --host 0.0.0.0 makes the server listen on all available network interfaces,
# which is necessary for it to be accessible from outside the container.
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
