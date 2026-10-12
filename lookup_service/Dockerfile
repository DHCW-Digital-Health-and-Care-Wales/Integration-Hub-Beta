FROM python:3.13-slim-bookworm

# Install uv by copying from image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Add certificates for proxied networks
COPY --from=ca-certs ./*.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

WORKDIR /app/lookup_service

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install the project's dependencies using the lockfile and settings
RUN uv --native-tls sync --locked --no-install-project --no-dev

# Copy the source code and seed data, then install the project
COPY lookup_service/ /app/lookup_service/lookup_service
COPY seed/ /app/lookup_service/seed
RUN uv --native-tls sync --locked --no-dev

# Place executables in the environment at the front of the path
ENV PATH="/app/lookup_service/.venv/bin:$PATH"
ENV LOOKUP_SEED_DIR=/app/lookup_service/seed

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

EXPOSE 8080

CMD ["python", "-m", "lookup_service.application"]
