# Dockerfile
# Use an official Python runtime as a parent image.
# Using a slim image reduces the final image size.
FROM python:3.11-slim

# Set the working directory in the container to /app
WORKDIR /app

# Set the PYTHONPATH environment variable.
# This ensures that Python can find modules within the /app directory,
# which is crucial for making absolute imports from 'src' work correctly.
ENV PYTHONPATH "${PYTHONPATH}:/app"

# Copy the dependency files into the container.
COPY requirements.txt constraints.txt ./

# Install the Python dependencies specified in requirements.txt.
# --no-cache-dir is used to reduce the image size by not storing the pip cache.
# -c constraints.txt is used to enforce specific versions for dependencies if needed.
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

# Copy the entire 'src' directory from the host into the container at /app/src.
# This brings all your application source code into the image.
COPY src/ /app/src/

# Copy the entrypoint script into the container and make it executable.
# This script often contains logic to wait for dependencies (like databases)
# or run initial setup tasks before the main application starts.
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# The CMD or ENTRYPOINT to run the specific service will be provided
# in the docker-compose.yaml or Kubernetes manifest. This makes the image
# reusable for different services (e.g., ai_service, tarpit_api, etc.).
