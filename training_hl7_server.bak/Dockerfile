# Dockerfile - Instructions for building a Docker container image
# This creates a lightweight Linux container with Python and our application

# Start from the official Python 3.13 slim image
# "slim" means a minimal image with just Python (no build tools)
FROM python:3.13-slim

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
# This ensures that Python output appears immediately in docker logs
ENV PYTHONUNBUFFERED=1

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Set the working directory inside the container
# All subsequent commands will run from this directory
WORKDIR /app

# ===================================================================
# Install uv - a fast Python package manager
# ===================================================================
# Copy the uv binaries from the official uv image
# This is more efficient than downloading and installing uv separately
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# ===================================================================
# Copy application files into the container
# ===================================================================
# Copy the project configuration file
COPY pyproject.toml uv.lock ./

# WEEK 2 ADDITION: Copy shared_libs for message_bus_lib dependency
# The pyproject.toml references "../shared_libs/message_bus_lib"
# In docker-compose, this comes from additional_contexts
# The COPY uses the context name "shared_libs" which docker-compose maps
COPY --from=shared_libs . /shared_libs

# ===================================================================
# Install Python dependencies (two-stage process)
# ===================================================================
# Stage 1: Install dependencies only (faster Docker layer caching)
# This layer only rebuilds when pyproject.toml or uv.lock changes
RUN uv --native-tls sync --locked --no-install-project --no-dev
# --native-tls: Use system SSL certificates
# --locked: Use exact versions from uv.lock (fail if lockfile is missing)
# --no-install-project: Only install dependencies, not the project itself
# --no-dev: Skip development dependencies (ruff, mypy, pytest)

# Stage 2: Copy application code and install the project
# This layer rebuilds whenever your Python code changes
COPY training_hl7_server/ /app/training_hl7_server/
RUN uv --native-tls sync --locked --no-dev
# Now the project itself is installed into the virtual environment

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
CMD ["python", "-m", "training_hl7_server.application"]