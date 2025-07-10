# For more information, please refer to https://aka.ms/vscode-docker-python
FROM python:3.13-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Add certificates for proxied networks
COPY --from=ca-certs ./*.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates

WORKDIR /app

# Copy shared libraries
COPY --from=shared_libs . /shared_libs

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install the project's dependencies using the lockfile and settings
RUN uv --native-tls sync --locked --no-install-project --no-dev

# Copy the rest of the project source code and install it
COPY hl7_server/ /app/hl7_server/
RUN uv sync --locked --no-dev

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

# Run the application
CMD ["python", "-m", "hl7_server.application"]
