FROM python:3.13-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY --from=ca-certs ./*.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates

WORKDIR /app/transformers/lims_trrr_mapper

COPY --from=shared_libs . /app/shared_libs
COPY pyproject.toml uv.lock ./
RUN uv --native-tls sync --locked --no-install-project --no-dev

COPY lims_trrr_mapper/ /app/transformers/lims_trrr_mapper/lims_trrr_mapper
RUN uv --native-tls sync --locked --no-dev

ENV PATH="/app/transformers/lims_trrr_mapper/.venv/bin:$PATH"
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

CMD ["python", "-m", "lims_trrr_mapper.application"]
