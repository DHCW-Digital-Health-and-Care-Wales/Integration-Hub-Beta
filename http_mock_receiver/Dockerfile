FROM python:3.13-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv --native-tls sync --locked --no-install-project --no-dev

COPY http_mock_receiver/ /app/http_mock_receiver/
RUN uv --native-tls sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"

RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

EXPOSE 8080

CMD ["python", "-m", "http_mock_receiver"]
