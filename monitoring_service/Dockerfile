FROM python:3.13-slim-bookworm

WORKDIR /app

# Install system dependencies for pyodbc
RUN apt-get update && apt-get install -y \
    unixodbc \
    unixodbc-dev \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY monitoring_service/ ./monitoring_service/
COPY config.ini .

CMD ["python", "-m", "monitoring_service.monitoring_service"]