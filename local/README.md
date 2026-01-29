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

### Service Bus Emulator Configuration

The [ServiceBusEmulatorConfig.json](./ServiceBusEmulatorConfig.json) file defines the queues and topics used by the local Service Bus emulator. This configuration creates the message routing infrastructure that connects all the services.

**What's inside:**

- **Queues**: Named channels where messages wait to be processed (e.g., `local-inthub-phw-transformer-ingress`)
- **Queue Properties**: Settings like message retention time (`DefaultMessageTimeToLive`), lock duration, and session support

**Adding a new queue:**

1. Open `ServiceBusEmulatorConfig.json`
2. Add a new queue entry under `Namespaces[0].Queues[]`:

```json
{
  "Name": "local-inthub-my-new-queue",
  "Properties": {
    "DeadLetteringOnMessageExpiration": false,
    "DefaultMessageTimeToLive": "PT1H",
    "DuplicateDetectionHistoryTimeWindow": "PT20S",
    "ForwardDeadLetteredMessagesTo": "",
    "ForwardTo": "",
    "LockDuration": "PT1M",
    "MaxDeliveryCount": 10,
    "RequiresDuplicateDetection": false,
    "RequiresSession": true
  }
}
```

3. Rebuild the Service Bus emulator container: `docker compose build sb-emulator`
4. Restart the stack with your desired profile

**Common queue naming pattern:** `local-inthub-{service}-{ingress|egress}`

> [!NOTE]
> **RequiresSession**: Set to `true` when you need guaranteed FIFO (First-In-First-Out) message ordering. Session-enabled queues ensure messages with the same session ID are processed in order. This applies to both the local emulator and Azure Service Bus in production.

### SSL Certificates (Corporate Networks)

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

#### Profiles Reference

Each profile starts a complete integration flow with all required services:

| Profile          | Services Started                                                                            | Use Case                                                             |
| ---------------- | ------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| **phw-to-mpi**   | phw-hl7-server, phw-hl7-transformer, mpi-hl7-sender, mpi-hl7-mock-receiver, sb-emulator     | PHW (Public Health Wales) to MPI integration flow                    |
| **paris-to-mpi** | paris-hl7-server, mpi-hl7-sender, mpi-hl7-mock-receiver, sb-emulator                        | Paris healthcare system to MPI integration flow (no transformation)  |
| **chemo-to-mpi** | chemo-hl7-server, chemo-hl7-transformer, mpi-hl7-sender, mpi-hl7-mock-receiver, sb-emulator | Chemocare system to MPI integration flow                             |
| **pims-to-mpi**  | pims-hl7-server, pims-hl7-transformer, mpi-hl7-sender, mpi-hl7-mock-receiver, sb-emulator   | PIMS (Patient Information Management System) to MPI integration flow |

#### Environment Files Reference

Each service is configured via a corresponding `.env` file in the `local/` directory:

| File                          | Configures            | Key Variables                                                             |
| ----------------------------- | --------------------- | ------------------------------------------------------------------------- |
| **phw-hl7-server.env**        | PHW HL7 Server        | `PORT=2575`, `EGRESS_QUEUE_NAME`, `HL7_VALIDATION_FLOW=phw`               |
| **phw-hl7-transformer.env**   | PHW Transformer       | `INGRESS_QUEUE_NAME`, `EGRESS_QUEUE_NAME`, `WORKFLOW_ID=phw-to-mpi`       |
| **paris-hl7-server.env**      | Paris HL7 Server      | `PORT=2577`, `EGRESS_QUEUE_NAME`, `HL7_VALIDATION_FLOW=paris`             |
| **chemo-hl7-server.env**      | Chemocare HL7 Server  | `PORT=2578`, `EGRESS_QUEUE_NAME`, `HL7_VALIDATION_FLOW=chemo`             |
| **chemo-hl7-transformer.env** | Chemocare Transformer | `INGRESS_QUEUE_NAME`, `EGRESS_QUEUE_NAME`, `WORKFLOW_ID=chemocare-to-mpi` |
| **pims-hl7-server.env**       | PIMS HL7 Server       | `PORT=2579`, `EGRESS_QUEUE_NAME`, `HL7_VALIDATION_FLOW=pims`              |
| **pims-hl7-transformer.env**  | PIMS Transformer      | `INGRESS_QUEUE_NAME`, `EGRESS_QUEUE_NAME`, `WORKFLOW_ID=pims-to-mpi`      |
| **mpi-hl7-sender.env**        | MPI HL7 Sender        | `INGRESS_QUEUE_NAME`, `RECEIVER_MLLP_HOST`, `MAX_MESSAGES_PER_MINUTE=30`  |
| **mpi-hl7-mock-receiver.env** | MPI Mock Receiver     | `PORT=2576`, `EGRESS_QUEUE_NAME`                                          |

> **Note**: All services share the same Service Bus connection string which is configured to use the local emulator.

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

- Install python-hl7 e.g. `pip install hl7` - see [python-hl7 docs](https://python-hl7.readthedocs.io/en/latest/#install)
- Create a `.hl7` file to contain the HL7 message to be sent (or use the `phw-to-mpi.sample.hl7` example file)
- Run `mllp_send` with the `.hl7` file e.g. `mllp_send --loose --file phw-to-mpi.sample.hl7 --port 2575 127.0.0.1`
- Check the Docker logs to show whether the request succeeded.

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

## Using Just

There is a `justfile` to streamline common tasks for local development using [Just](https://github.com/casey/just), a modern command runner.

### Installation

Install Just, see the [Just installation guide](https://github.com/casey/just#installation).

### Available Commands

Execute `just --list` to see all available commands. Key commands include:

```
  install          Install Python dependencies (hl7).
  secrets          Generate the .secrets file.
  build <profile>  Build (or rebuild) Docker containers for a profile.
  start <profile>  Start Docker containers for a profile.
  send <file> [port=<port>]  Send a HL7 message (default port: 2575).
  logs [service]   Follow logs from services (all or specific service).
  stop             Stop all Docker containers.
  run [profile]    Complete setup: install, generate secrets, and optionally start services.
  restart <profile> Rebuild and restart services.
  clean            Stop all containers and remove secrets file.
```

Examples:

```bash
  just start phw-to-mpi
  just send phw-to-mpi.sample.hl7
  just send phw-to-mpi.sample.hl7 2576
  just logs mpi-hl7-mock-receiver
  just stop
  just build phw-to-mpi
  just run phw-to-mpi     # Complete setup and start in one command
```

## DevContainer Usage

It is possible to run 'locally` using GitHub Dev Containers:

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/DHCW-Digital-Health-and-Care-Wales/Integration-Hub-Beta/?quickstart=1)

Note: It can take a few minutes to fully launch Codespaces the first time, but
is faster on subsequent launches as the environment is then cached.

This provides:

- A pre-configured VS Code environment (with useful extensions installed - such as Container Management)
- Ability to work in a 'Browser` based UI e.g. via Edge/Chrome or the desktop VS Code application.
- A virtual development environment, removing the need to install any software locally.
- Access to a Linux `Terminal` with `Docker` and `Just` installed to manage containers.
- The ability to run and test the whole system.

### Quick Start with DevContainer

Once you have successfully launched a Codespace:

1. **Just is automatically installed** in the DevContainer (no manual installation needed)
2. **Discover available commands**: Run `just --list` to see all available commands
3. **Quick start**: Run `just run phw-to-mpi` to install dependencies, generate secrets, and start services in one command
4. **Manual setup** (if preferred):
   - Install dependencies: `just install`
   - Generate secrets: `just secrets`
   - Start a profile: `just start <profile-name>`

For more details, see [Using Just](#using-just).
