FROM python:3.13-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app/senders/soap_subscription_sender

# Copy shared libraries
COPY --from=shared_libs . /app/shared_libs

COPY pyproject.toml uv.lock ./
RUN uv --native-tls sync --locked --no-install-project --no-dev

COPY soap_subscription_sender/ /app/senders/soap_subscription_sender/soap_subscription_sender/
RUN uv --native-tls sync --locked --no-dev

ENV PATH="/app/senders/soap_subscription_sender/.venv/bin:$PATH"

RUN adduser -u 5678 --disabled-password --gecos "" appuser \
    && chown -R appuser /app
USER appuser

CMD ["python", "-m", "soap_subscription_sender.application"]
