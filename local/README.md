# Running Integration Hub locally

Integration Hub services can be run locally using [Azure Service Bus emulator](https://learn.microsoft.com/en-us/azure/service-bus-messaging/overview-emulator) and [Docker Compose](https://docs.docker.com/compose/).

## Table of Contents

- [Quick Start Commands](#quick-start-commands)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
  - [Service Bus Emulator Configuration](#service-bus-emulator-configuration)
  - [Local PostgreSQL](#local-postgresql)
  - [Connecting to PostgreSQL from Your Machine](#connecting-to-postgresql-from-your-machine)
  - [Local PostgreSQL](#local-postgresql)
  - [Connecting to PostgreSQL from Your Machine](#connecting-to-postgresql-from-your-machine)
  - [macOS-Specific Setup](#macos-specific-setup)
  - [SSL Certificates (Corporate Networks)](#ssl-certificates-corporate-networks)
- [Startup](#startup)
  - [Build and start containers](#build-and-start-containers)
  - [Review logs](#review-logs)
  - [Rebuilding Containers](#rebuilding-containers)
  - [Interact with Azure Service Bus emulator](#interact-with-azure-service-bus-emulator)
  - [Using Python MLLP Send to test](#using-python-mllp-send-to-test)
  - [Using the HAPI test panel](#using-the-hapi-test-panel-to-connect-to-the-service-bus-emulator-macos)
  - [Running the Message Replay Job](#running-the-message-replay-job)
  - [Stopping the stack](#stopping-the-stack)
- [Using Just](#using-just)
- [DevContainer Usage](#devcontainer-usage)

> [!IMPORTANT]
> To run `just` commands in the `local/` directory, you must first set up a Python virtual environment using `uv venv` with no dependencies. Run this once in the `local/` folder:
>
> ```bash
> # in local/
> uv venv
> ```
>
> This creates a `.venv` directory that `just` uses. Remember to `source .venv/bin/activate` before using just

## Quick Start Commands

Common tasks for local development:

| Task                                  | Command                                                        |
| ------------------------------------- | -------------------------------------------------------------- |
| Generate secrets                      | `just secrets`                                                 |
| Start PHW integration flow            | `just start phw-to-mpi`                                        |
| Start all profiles                    | `docker compose --profile "*" up -d`                           |
| View live logs (all services)         | `just logs`                                                    |
| View logs for specific service        | `just logs mpi-hl7-mock-receiver`                              |
| Send test HL7 message                 | `just send ./sample_messages/phw-to-mpi.sample.hl7`            |
| Send test HL7 message to a given port | `just send ./sample_messages/chemocare-to-mpi.sample.hl7 2578` |
| Run the message replay job            | `just run replay`                                              |
| Stop all containers                   | `just stop`                                                    |

For more commands, run `just --list`.

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

### Local PostgreSQL

A local PostgreSQL instance is available for development and testing. The container uses the official `postgres:16-bookworm` image and automatically initialises the `integrationhub` database with the required schema.

**Connection Details:**

| Property     | Value                                      |
| ------------ | ------------------------------------------ |
| **Host**     | `localhost`                                |
| **Port**     | `5432`                                     |
| **Database** | `integrationhub`                           |
| **Username** | `inthub`                                   |
| **Password** | Value of `POSTGRES_PASSWORD` in `.secrets` |

**Connection String:**

```
postgresql://inthub:<POSTGRES_PASSWORD>@<localhost|postgres>:5432/integrationhub?sslmode=disable
```

**What's initialised:**

- Database: `integrationhub`
- Schema: `monitoring`
- Table: `monitoring.message` - stores message tracking data including payloads, timestamps, and workflow identifiers
- Table: `monitoring.message_replay_queue` - used for re-sending messages from the Message Store to the Service Bus priority queue, includes a replay id, the message replay status, the message id from the `message` table and replay batch identifier

> Identifiers are lower-case `snake_case`. PostgreSQL folds unquoted identifiers to lower case, so keeping the
> original `PascalCase` names would mean double-quoting every identifier in every query, forever.

**Customising initialisation:**

To modify the database schema or add seed data, edit the scripts in `sql-scripts/init/`. The `postgres` image runs every `.sql` file in that directory in filename order, but **only when the data volume is empty** — unlike the previous SQL Server entrypoint, they are not re-run on every start. To pick up schema changes, remove the volume with `docker compose down -v`.

**Message Store Service database configuration:**

The `message-store-service` connects to the local PostgreSQL container using the following environment variables, which are set in `message-store-service.env`:

| Variable      | Value            | Description                                                                    |
| ------------- | ---------------- | ------------------------------------------------------------------------------ |
| `PG_HOST`     | `postgres`       | Hostname of the PostgreSQL container on the Docker network                     |
| `PG_PORT`     | `5432`           | PostgreSQL port                                                                |
| `PG_DATABASE` | `integrationhub` | Database name                                                                  |
| `PG_USER`     | `inthub`         | Database role — required in **both** auth modes                                |
| `PG_SSLMODE`  | `disable`        | Overrides the default (`require`) — the local container has no TLS certificate |

> **Note**: `POSTGRES_PASSWORD` is injected via the `.secrets` file (not `message-store-service.env`). The same variable configures the `postgres` container itself, so one secret drives both the server and its clients. Omit it to use Managed Identity (production).

> **Note**: `PG_SSLMODE` defaults to `require` — the correct secure setting for Azure Database for PostgreSQL in production. The sample local env explicitly opts out.

**Starting PostgreSQL:**

The PostgreSQL container starts automatically when using any profile (e.g., `just start phw-to-mpi` or `docker compose --profile phw-to-mpi up -d`).

### Connecting to PostgreSQL from Your Machine

You can connect to the local PostgreSQL instance from your development machine using any PostgreSQL client. Use the connection details from [Local PostgreSQL](#local-postgresql).

**Using psql inside the container:**

```bash
docker compose exec postgres psql -U inthub -d integrationhub
```

**Using VS Code:**

1. Install a PostgreSQL extension, e.g. [PostgreSQL](https://marketplace.visualstudio.com/items?itemName=ms-ossdata.vscode-pgsql)
2. Add a connection using the details from [Local PostgreSQL](#local-postgresql)
3. Set the SSL mode to `disable` — the local container serves plain TCP with no certificate

### macOS-Specific Setup (for running Python services locally)

If you need to run Python-based services locally (such as the message replay job or message store service), follow these additional steps:

#### Database driver

No native driver installation is needed. `psycopg[binary]` bundles its own libpq, so `uv sync` is sufficient.

#### Apple Silicon (M series) Mac Setup

If you're using an Apple Silicon (M series) Mac, additional Docker configuration is required because the Service Bus emulator's SQL Edge backing store does not support the native ARM64 architecture:

1. **Open Docker Desktop settings**
2. Navigate to **Settings > General**
3. Under **Virtual machine manager**, select **Apple Virtualisation Framework**
4. Enable the checkbox: **Use Rosetta for x86_64/amd64 emulation on Apple Silicon**
5. Click **Apply & Restart**

This configuration allows Docker to run the SQL Edge container using x86/amd64 emulation when building or running locally.

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
- lims-to-mpi
- paris-to-mpi
- chemo-to-mpi
- pims-to-mpi
- mosaiq-to-mpi
- wds-to-mpi
- mpi-to-topic

#### Profiles Reference

Each profile starts a complete integration flow with all required services:

| Profile          | Services Started                                                                            | Use Case                                                                                          |
| ---------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| **phw-to-mpi**   | phw-hl7-server, phw-hl7-transformer, mpi-hl7-sender, mpi-hl7-mock-receiver, sb-emulator     | PHW (Public Health Wales) to MPI integration flow                                                 |
| **lims-to-mpi**  | hl7-soap-server, mpi-hl7-sender, mpi-hl7-mock-receiver, sb-emulator                          | LIMS SOAP HL7 XML ingress (assigning authority 328) to MPI integration flow (no transformer yet)  |
| **paris-to-mpi** | paris-hl7-server, mpi-hl7-sender, mpi-hl7-mock-receiver, sb-emulator                        | Paris healthcare system to MPI integration flow (no transformation)                               |
| **chemo-to-mpi** | chemo-hl7-server, chemo-hl7-transformer, mpi-hl7-sender, mpi-hl7-mock-receiver, sb-emulator | Chemocare system to MPI integration flow                                                          |
| **pims-to-mpi**  | pims-hl7-server, pims-hl7-transformer, mpi-hl7-sender, mpi-hl7-mock-receiver, sb-emulator   | PIMS (Patient Information Management System) to MPI integration flow                              |
| **mosaiq-to-mpi** | mosaiq-hl7-server, mpi-hl7-sender, mpi-hl7-mock-receiver, sb-emulator                       | Mosaiq oncology system to MPI integration flow (no transformation)                                |
| **wds-to-mpi**   | wds-hl7-server, mpi-hl7-sender, mpi-hl7-mock-receiver, sb-emulator                          | WDS to MPI integration flow (no transformation)                                                   |
| **replay**       | message-replay-job                                                                          | The message replay job moving messages from PostgreSQL to an Azure Service Bus priority queue |
| **mpi-to-topic** | mpi-hl7-server, mpi-hl7-chemo-sender                                                        | MPI to outbound SWW Chemocare integration flow                                                    |

Note that all the listed profiles will start the **message-store-service** as well as it is not tagged with a profile.

#### Environment Files Reference

Each service is configured via a corresponding `.env` file in the `local/` directory:

| File                          | Configures                  | Key Variables                                                                         |
| ----------------------------- | --------------------------- | ------------------------------------------------------------------------------------- |
| **phw-hl7-server.env**        | PHW HL7 Server              | `PORT=2575`, `EGRESS_QUEUE_NAME`, `HL7_VALIDATION_FLOW=phw`                           |
| **lims-soap-hl7-server.env**  | HL7 SOAP Server             | `PORT=8080`, `SOAP_ENDPOINT_PATH=/soap`, `ALLOWED_ASSIGNING_AUTHORITIES=328`           |
| **phw-hl7-transformer.env**   | PHW Transformer             | `INGRESS_QUEUE_NAME`, `EGRESS_QUEUE_NAME`, `WORKFLOW_ID=phw-to-mpi`                   |
| **paris-hl7-server.env**      | Paris HL7 Server            | `PORT=2577`, `EGRESS_QUEUE_NAME`, `HL7_VALIDATION_FLOW=paris`                         |
| **mosaiq-hl7-server.env**     | Mosaiq HL7 Server           | `PORT=2583`, `EGRESS_QUEUE_NAME`, `HL7_VALIDATION_FLOW=mosaiq`                        |
| **chemo-hl7-server.env**      | Chemocare HL7 Server        | `PORT=2578`, `EGRESS_QUEUE_NAME`, `HL7_VALIDATION_FLOW=chemo`                         |
| **chemo-hl7-transformer.env** | Chemocare Transformer       | `INGRESS_QUEUE_NAME`, `EGRESS_QUEUE_NAME`, `WORKFLOW_ID=chemocare-to-mpi`             |
| **pims-hl7-server.env**       | PIMS HL7 Server             | `PORT=2579`, `EGRESS_QUEUE_NAME`, `HL7_VALIDATION_FLOW=pims`                          |
| **pims-hl7-transformer.env**  | PIMS Transformer            | `INGRESS_QUEUE_NAME`, `EGRESS_QUEUE_NAME`, `WORKFLOW_ID=pims-to-mpi`                  |
| **wds-hl7-server.env**        | WDS HL7 Server              | `PORT=2582`, `EGRESS_QUEUE_NAME`, `HL7_VALIDATION_FLOW=wds`                           |
| **message-store-service.env** | Message Store Service       | `INGRESS_QUEUE_NAME`, `SQL_SERVER`, `SQL_DATABASE`                                    |
| **message-replay-job.env**    | Message Replay Job          | `REPLAY_BATCH_ID`, `PRIORITY_QUEUE_NAME`, `SQL_SERVER`, `SQL_DATABASE`                |
| **mpi-hl7-sender.env**        | MPI HL7 Sender              | `INGRESS_QUEUE_NAME`, `RECEIVER_MLLP_HOST`, `MAX_MESSAGES_PER_MINUTE=30`              |
| **mpi-hl7-mock-receiver.env** | MPI Mock Receiver           | `PORT=2576`, `EGRESS_QUEUE_NAME`                                                      |
| **mpi-hl7-chem-sender.env**   | MPI HL7 Subscription Sender | `PORT=2581`, `INGRESS_TOPIC_NAME`, `INGRESS_SUBSCRIPTION_NAME`, `INGRESS_SESSION_ID`  |

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
- Create a `.hl7` file to contain the HL7 message to be sent (or use the `phw-to-mpi.sample.hl7` example file in `local/sample_messages/`)
- Run `mllp_send` with the `.hl7` file e.g. `mllp_send --loose --file /sample_messages/phw-to-mpi.sample.hl7 --port 2575 127.0.0.1`
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

### Running the Message Replay Job

The message replay job allows you to re-send messages from the Message Store to the Service Bus priority queue. This is useful for operational support when messages need to be reprocessed.

For detailed setup and execution instructions, see [MESSAGE_REPLAY.md](./MESSAGE_REPLAY.md).

### Stopping the stack

To terminate the containers you can proceed with the following command in the `/local` directory:

```
just stop
```

or its equivalent:

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
  just send ./sample_messages/phw-to-mpi.sample.hl7
  just send ./sample_messages/chemocare-to-mpi.sample.hl7 2578
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
