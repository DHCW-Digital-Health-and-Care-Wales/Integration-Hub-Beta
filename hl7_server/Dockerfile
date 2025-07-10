# For more information, please refer to https://aka.ms/vscode-docker-python
FROM python:3.13-slim-bookworm

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Add certificates for proxied networks
COPY --from=ca-certs . /opt/ca-certs

ENV SSL_CERT_FILE=/opt/ca-certs/cacerts.pem
ENV REQUESTS_CA_BUNDLE=/opt/ca-certs/cacerts.pem
ENV CURL_CA_BUNDLE=/opt/ca-certs/cacerts.pem

# Install uv by copying from image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

WORKDIR /app

# Copy shared libraries
COPY --from=shared_libs . /shared_libs

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install the project's dependencies using the lockfile and settings
RUN SSL_CERT_FILE=/opt/ca-certs/cacerts.pem \
    REQUESTS_CA_BUNDLE=/opt/ca-certs/cacerts.pem \
    CURL_CA_BUNDLE=/opt/ca-certs/cacerts.pem \
    uv sync --locked --no-install-project --no-dev \
    --trusted-host pypi.org \
    --trusted-host pypi.python.org \
    --trusted-host files.pythonhosted.org

# Copy the rest of the project source code and install it
COPY hl7_server/ /app/hl7_server/
RUN SSL_CERT_FILE=/opt/ca-certs/cacerts.pem \
    REQUESTS_CA_BUNDLE=/opt/ca-certs/cacerts.pem \
    CURL_CA_BUNDLE=/opt/ca-certs/cacerts.pem \
    uv sync --locked --no-dev \
    --trusted-host pypi.org \
    --trusted-host pypi.python.org \
    --trusted-host files.pythonhosted.org

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

# Run the application
CMD ["python", "-m", "hl7_server.application"]