FROM python:3.13-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv --native-tls sync --locked --no-install-project --no-dev
COPY workflow_designer/ /app/workflow_designer/
RUN uv --native-tls sync --locked --no-dev
ENV PATH="/app/.venv/bin:$PATH"
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser
EXPOSE 8080
CMD ["gunicorn", "workflow_designer.app:app", "--bind", "0.0.0.0:8080", "--workers", "2"]
