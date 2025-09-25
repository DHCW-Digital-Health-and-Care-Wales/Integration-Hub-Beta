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

  # Run to refresh ~/.zshrc

  source ~/.zshrc

  **For Docker containers:**
  Provide custom CA certificates if needed (required in some proxied corporate networks): merge them in a single crt (change extension if needed) file and add in every service under `./ca-certs/cacerts.crt` path.

## Startup

### Build and start containers

Profiles:

- phw-to-mpi
- paris-to-mpi
- chemo-to-mpi
- pims-to-mpi

The profile flag can be repeated to start multiple profiles or if you want to enable all profiles at the same time, you can use the flag --profile "\*"

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

### Using the HAPI test panel to connect to the Service Bus Emulator (macOS)

**Pre-requisites**

- openjdk - install either standalone or (better) using sdkman to manage java versions
- Docker containers need to be running with the profile of the service(s) desired - see [Build and start containers](#build-and-start-containers)

**Steps**

1. Download the latest **hapi-dist-[version]-testpanel.tar.gz** release from https://github.com/hapifhir/hapi-hl7v2/releases
2. Unpack.
3. Navigate to the dir where it was unpacked using the terminal.
4. run `bash testpanel.sh`
5. HAPI TestPanel should launch.
6. On the left hand side under **Sending Connections** click on the plus sign ⊕
7. using PHW as an example (adjust port number for other services):

- select Single Port MLLP
- set the port number to 2575
- Click Start to test the connection - you should see `Successfully connected to localhost:2575` in the log.

8. On the left hand side under **Messages** click on the plus sign ⊕ to create a new message with the desired HL7 version and message type.

9. At the top of the window set the sending connection to the one created prior using the **Send** dropdown and click the green Send button located to the right.

10. Logs would show whether your request succeeded.

### Stopping the stack

To terminate the containers you can proceed with the following command in the `/local` directory:

```
docker compose down
```
