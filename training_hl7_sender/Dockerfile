# Dockerfile - Training HL7 Sender Container Image
# ======================================================
# This creates a lightweight Linux container with Python and the sender.

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
WORKDIR /app

# ===================================================================
# Install uv - a fast Python package manager
# ===================================================================
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# ===================================================================
# Copy shared_libs for message_bus_lib and processor_manager_lib
# ===================================================================
# The pyproject.toml references "../shared_libs/..."
# In docker-compose, these come from additional_contexts
# The COPY uses the context name "shared_libs" which docker-compose maps
COPY --from=shared_libs . /shared_libs

# ===================================================================
# Copy application files into the container
# ===================================================================
COPY pyproject.toml uv.lock ./

# ===================================================================
# Install Python dependencies (two-stage process)
# ===================================================================
# Stage 1: Install dependencies only (faster Docker layer caching)
RUN uv --native-tls sync --locked --no-install-project --no-dev

# Stage 2: Copy application code and install the project
COPY training_hl7_sender/ /app/training_hl7_sender/
RUN uv --native-tls sync --locked --no-dev

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Creates a non-root user for security
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

# Run the sender application
CMD ["python", "-m", "training_hl7_sender.application"]