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

### Rebuilding Containers

If you make changes to a service after the containers have previously been
built, you may need to rebuild the containers in order for those changes to be
incorporated:

```
docker compose --profile <profile-name> build
```

Then re-start the containers as per [Build and start containers](#build-and-start-containers)

### Interact with Azure Service Bus emulator

You can connect to Azure Service Bus emulator from the local machine using following connection string:

```
"Endpoint=sb://127.0.0.1;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=SAS_KEY_VALUE;UseDevelopmentEmulator=true;"
```

### Using Python MLLP Send to test

**Pre-requisites**

- [python-hl7](https://pypi.org/project/hl7/) installed locally
- Docker containers need to be running with the profile of the service(s) desired - see [Build and start containers](#build-and-start-containers)

**Steps**

* Install python-hl7 e.g. `pip install hl7` - see [python-hl7 docs](https://python-hl7.readthedocs.io/en/latest/#install)
* Create a `.hl7` file to contain the HL7 message to be sent (or use the `phw-to-mpi.sample.hl7` example file)
* Run `mllp_send` with the `.hl7` file e.g. `mllp_send --loose --file phw-to-mpi.sample.hl7 --port 2575 127.0.0.1`
* Check the Docker logs to show whether the request succeeded.

See [mllp_send](https://python-hl7.readthedocs.io/en/latest/mllp_send.html) for more info.

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
docker compose --profile "*" down
```

## Using Make

There is a `Makefile` to streamline commmon tasks for local development.

Execute `make help` to see instructions, in summary:

Targets:
```
  install   Install Python dependencies (hl7).
  secrets   Force generation of the .secrets file.
  build     Build (or rebuild) Docker containers. (Usage: make build <profile>)
  start     Start Docker containers. (Usage: make start <profile>)
  send      Send a HL7 message. (Usage: make send file=<filename> [port=<port>])
  logs      Follow logs from services. (Usage: make logs <service_name>)
  stop      Stop all Docker containers.
```
	
Examples:
```bash
  make start phw-to-mpi
  make send file=test_message.hl7
	make send file=test_message.hl7 port=2576
  make logs mpi-hl7-mock-receiver
  make stop
  make build phw-to-mpi
```

## DevContainer Usage

It is possible to run 'locally` using GitHub Dev Containers:

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/DHCW-Digital-Health-and-Care-Wales/Integration-Hub-Beta/?quickstart=1)

Note: It can take a few minutes to fully launch Codespaces the first time, but
is faster on subsequent launches as the environment is then cached.

This provides:

* A pre-configured VS Code environment (with useful extensions installed - such as Container Management)
* Ability to work in a 'Browser` based UI e.g. via Edge/Chrome or the desktop VS Code application.
* A virtual development environment, removing the need to install any software locally.
* Access to a Linux `Terminal` with `Docker` installed to manage containers.
* The ability to run and test the whole system.

Once you have successfully launched a Codespace you can follow the steps in this README, preferrably via `make` see [Using Make](#using-make).