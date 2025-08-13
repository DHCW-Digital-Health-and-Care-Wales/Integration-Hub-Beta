# Running Integration Hub locally

Integration Hub services can be run locally using [Azure Service Bus emulator](https://learn.microsoft.com/en-us/azure/service-bus-messaging/overview-emulator) and [Docker Compose](https://docs.docker.com/compose/).

## Prerequisites

- [Docker Desktop](https://docs.docker.com/desktop/)
- Minimum hardware Requirements:
    - 2 GB RAM
    - 5 GB of Disk space
- WSL Enablement (Only for Windows):
    - [Install Windows Subsystem for Linux (WSL) | Microsoft Learn](https://learn.microsoft.com/en-us/windows/wsl/install)
    - [Configure Docker to use WSL](https://docs.docker.com/desktop/features/wsl/)

## Configuration

- Create required `.secrets` file from the `.secrets-template` in `local` folder: 
```
python3 generate_secrets.py > .secrets
```

- Amend queues, topics and subscriptions configuration when needed in [ServiceBusEmulatorConfig.json](./ServiceBusEmulatorConfig.json).

- **For machines on corporate networks**: Configure SSL certificates to allow uv and Docker to work with corporate proxies:

    **For local development (uv sync):**
    ```bash
    # Add to your shell profile (~/.zshrc)
    export SSL_CERT_FILE=/path/to/your/corporate-certificate.pem
    ```
    # Run to refresh /.zshrc
    source ~/.zshrc

    **For Docker containers:**
    Provide custom CA certificates if needed (required in some proxied corporate networks): merge them in a single crt (change extension if needed) file and add in every service  under `./ca-certs/cacerts.crt` path.

## Startup

### Build and start containers
Profiles:
- phw-to-mpi
- paris-to-mpi
- chemo-to-mpi
- pims-to-mpi

The profile flag can be repeated to start multiple profiles or if you want to enable all profiles at the same time, you can use the flag --profile "*"
```
docker compose --profile <profile-name> up -d
```

### Review logs

You can view logs from whole stack with:
```
docker compose logs -f
```
or from selected container
```
docker compose logs -f ${CONTAINER_NAME}
```

### Interact with Azure Service Bus emulator

You can connect to Azure Service Bus emulator from the local machine using following connection string:

```
"Endpoint=sb://127.0.0.1;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=SAS_KEY_VALUE;UseDevelopmentEmulator=true;"
```

### Stopping the stack
To terminate the containers you can proceed with the following command in the `/local` directory:

```
docker compose down
```
