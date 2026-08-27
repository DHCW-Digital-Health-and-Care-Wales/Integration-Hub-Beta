FROM python:3.13-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY --from=ca-certs ./*.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates

WORKDIR /app

COPY --from=shared_libs . /shared_libs

COPY pyproject.toml uv.lock ./
RUN uv --native-tls sync --locked --no-install-project --no-dev

COPY hl7_wds_transformer/ /app/hl7_wds_transformer/
RUN uv --native-tls sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"

RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

CMD ["python", "-m", "hl7_wds_transformer.application"]
