# For more information, please refer to https://aka.ms/vscode-docker-python
FROM python:3.13-slim

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Add certificates for proxied networks
COPY --from=ca-certs . /opt/ca-certs

ENV SSL_CERT_FILE=/opt/ca-certs/cacerts.pem
ENV REQUESTS_CA_BUNDLE=/opt/ca-certs/cacerts.pem
ENV CURL_CA_BUNDLE=/opt/ca-certs/cacerts.pem

# Install uv
# RUN pip install uv
RUN pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org uv

WORKDIR /build

# Copy dependency files
COPY pyproject.toml uv.lock ./
COPY --from=shared_libs . /shared_libs

# Install dependencies with uv
RUN uv sync --frozen --no-dev

WORKDIR /app

COPY hl7_server/ /app/hl7_server/

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
CMD ["uv", "run", "python", "-m", "hl7_server.application"]
