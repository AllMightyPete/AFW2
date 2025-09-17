# User Guide: Docker

This document explains how to use the Asset Processor Tool with Docker.

## Overview

A `Dockerfile` and `requirements-docker.txt` are provided to allow you to build and run the Asset Processor Tool in a containerized environment. This is primarily intended for CLI or monitor usage.

## Building the Docker Image

From the project root directory, run the following command to build the Docker image:

```bash
docker build -t asset-processor-tool .
```

This command builds a Docker image named `asset-processor-tool` using the `Dockerfile` in the current directory.

## Running the Docker Container

You can run the Docker container using standard Docker commands. You will typically need to mount volumes to make your input assets and desired output directory accessible within the container.

Here is an example run command (adjust volumes as needed):

```bash
docker run -v /path/to/your/inputs:/data/input -v /path/to/your/outputs:/data/output asset-processor-tool python main.py /data/input/YourAsset.zip -p YourPreset
```

*   `-v /path/to/your/inputs:/data/input`: This mounts your local input directory (`/path/to/your/inputs`) to the `/data/input` directory inside the container.
*   `-v /path/to/your/outputs:/data/output`: This mounts your local output directory (`/path/to/your/outputs`) to the `/data/output` directory inside the container.
*   `asset-processor-tool`: The name of the Docker image to run.
*   `python main.py /data/input/YourAsset.zip -p YourPreset`: The command to execute inside the container. This example runs the CLI with a specific input file and preset, using the mounted input and output directories.

Adjust the input file path (`/data/input/YourAsset.zip`) and preset name (`YourPreset`) as needed for your specific use case. You can also adapt the command to run the `monitor.py` script within the container.