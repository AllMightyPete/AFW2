# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables for default paths and settings
# These can be overridden at runtime using 'docker run -e VAR=VALUE ...'
ENV INPUT_DIR=/data/input
ENV OUTPUT_DIR=/data/output
ENV PROCESSED_DIR=/data/processed
ENV ERROR_DIR=/data/error
ENV LOG_LEVEL=INFO
ENV POLL_INTERVAL=5
ENV PROCESS_DELAY=2
# Calculate default workers based on typical container limits (can be overridden)
# This is a guess; adjust if needed or rely solely on runtime override.
ENV NUM_WORKERS=2

# Set the working directory in the container
WORKDIR /app

# Install system dependencies that might be needed by opencv-python or openexr
# (These are common dependencies; adjust if specific errors occur during build/runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    # Add dependencies for OpenEXR if needed (libopenexr-dev might be too large, check specific libs)
    # libopenexr25 # Example for Debian Bullseye/Bookworm, adjust based on base image OS version
 && rm -rf /var/lib/apt/lists/*

# Copy the specific requirements file for the Docker image
COPY requirements-docker.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements-docker.txt

# Copy the application code into the container
COPY main.py .
COPY monitor.py .
COPY asset_processor.py .
COPY configuration.py .
COPY config.py .

# Copy the presets directory
COPY Presets/ ./Presets/

# Make port 80 available to the world outside this container (if needed later, e.g., for a health check endpoint)
# EXPOSE 80

# Define the command to run the application
CMD ["python", "monitor.py"]