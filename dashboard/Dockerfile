# For more information, please refer to https://aka.ms/vscode-docker-python
FROM python:3.13-slim-bookworm

# Install uv by copying from image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

WORKDIR /app

# Copy dependency files and install dependencies first (layer cache)
COPY pyproject.toml uv.lock ./
RUN uv --native-tls sync --locked --no-install-project --no-dev

# Copy application source and install the project
COPY dashboard/ /app/dashboard/
COPY translations/ /app/translations/
RUN uv --native-tls sync --locked --no-dev

# Compile Babel translation catalogs (.po → .mo)
RUN uv run pybabel compile -d /app/translations

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

EXPOSE 8080

CMD ["gunicorn", "dashboard.app:app", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "60"]
