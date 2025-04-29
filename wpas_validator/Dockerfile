# For more information, please refer to https://aka.ms/vscode-docker-python
FROM python:3.13-slim

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Install pip requirements

WORKDIR /build/app
COPY requirements.txt .
COPY tmp/message_bus_lib /build/message_bus_lib
RUN ls -l /build/
RUN python -m pip install --no-cache-dir -r requirements.txt

# WORKDIR /
# RUN rm -rf /build

WORKDIR /
COPY . /app

# # Creates a non-root user with an explicit UID and adds permission to access the /app folder
# # For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
# RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
# USER appuser

# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
CMD ["python", "application.py"]