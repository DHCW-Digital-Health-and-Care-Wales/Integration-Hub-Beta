# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is the Integration Hub - Beta, a cloud-native platform for seamless and secure exchange of clinical information between disparate digital health systems within NHS Wales. The system follows a microservices architecture with event-driven messaging to connect various healthcare systems to the Master Patient Index (MPI).

## Architecture Overview

The platform consists of several microservices built around HL7 message processing:

1. **HL7 Servers** receive messages from healthcare systems via TCP/MLLP protocol
2. **Transformers** convert HL7 messages to target formats (HL7 v2.5) using business rules
3. **Service Bus** provides reliable message routing between services  
4. **Senders** deliver transformed messages to destination systems

The system uses a shared library architecture where common functionality is abstracted into libraries that all services depend on.

## Core Components

### HL7 Services
- `hl7_server/` - Generic HL7 message receiving server with MLLP support. Other servers (PHW, Paris, Chemo, PIMS) extend this service.
- `transformers/hl7_phw_transformer/` - Transforms PHW (Public Health Wales) messages to HL7v2.5
- `transformers/hl7_chemo_transformer/` - Transforms Chemocare system messages to HL7v2.5  
- `transformers/hl7_pims_transformer/` - Transforms PIMS (Patient Information Management System) messages to HL7v2.5
- `hl7_sender/` - Delivers transformed messages to target systems (MPI)
- `hl7_subscription_sender/` - Subscription-based delivery service
- `hl7_mock_receiver/` - Mock receiver for testing and development

### Shared Libraries
These are common libraries used across services:
- `health_check_lib/` - Standardized health check endpoints
- `message_bus_lib/` - Azure Service Bus integration and messaging patterns  
- `processor_manager_lib/` - Message processing orchestration
- `event_logger_lib/` - Azure Monitor / Application Insights event logging library
- `field_utils_lib/` - HL7 field parsing utilities
- `hl7_validation/` - HL7 schema validation helpers  
- `metric_sender_lib/` - Metrics sending to Azure Monitor
- `transformer_base_lib/` - Base classes for HL7 transformers

## Technology Stack

- Runtime: Python 3.13
- Package Management: UV (python package manager)
- Containerization: Docker & Docker Compose  
- Message Bus: Azure Service Bus (with local emulator support)
- Database: Azure SQL Edge (for local development)
- Architecture: Microservices with event-driven messaging
- Cloud Platform: Azure (cloud-native design)

## Development Workflow

### Local Setup and Testing

The project includes comprehensive local development setup using Docker Compose that can be managed with `just` commands. Key components for local development:

1. **Service Bus Emulator**: Provides local Azure Service Bus functionality  
2. **SQL Server Container**: For local database testing
3. **Docker Compose Profiles** for different integration flows:
   - `phw-to-mpi`, `paris-to-mpi`, `chemo-to-mpi`, `pims-to-mpi`
   - `replay` (message replay job)
   - `mpi-to-topic` (MPI to outbound)

### Quick Start Commands

```bash
# Generate secrets  
just secrets

# Start a specific integration flow (e.g., PHW to MPI)
just start phw-to-mpi

# View logs for a specific service
just logs mpi-hl7-mock-receiver

# Send test HL7 message  
just send ./sample_messages/phw-to-mpi.sample.hl7

# Run the message replay job
just run replay

# Stop all containers  
just stop
```

## Code Quality and Testing

The project uses:
- Ruff - Fast Python linter and formatter
- MyPy - Static type checking  
- Bandit - Security linter for Python code
- Unit testing framework (unittest)

Each service follows the same structure:
```
service_name/
├── Dockerfile
├── pyproject.toml  
├── uv.lock
├── service_name/           # Source code
├── tests/                  # Unit and integration tests  
└── README.md               # Service-specific documentation
```

## Build and Deployment

- Uses UV for Python dependency management  
- Azure DevOps pipelines for CI/CD in `pipeline-ado/`
- Infrastructure as Code with Terraform (separate repository)
- Services are containerized and deployed to Azure Container Apps

## Common Development Tasks

1. **Running Tests**: `uv run python -m unittest discover tests` in each service directory
2. **Code Quality Checks**: `uv run ruff check`, `uv run bandit`, `uv run mypy`
3. **Developing Transformers**: Extend the BaseTransformer class with custom transformation logic
4. **Adding New Services**: Use shared libraries, follow the same directory structure and conventions

## Key Patterns

1. **Service Bus Communication**: All services use the shared `message_bus_lib` for Azure Service Bus integration
2. **Health Checks**: TCP-based health checks implemented through `health_check_lib`
3. **Configuration Management**: Environment variables and configuration files for service settings  
4. **Message Validation**: HL7 validation implemented via `hl7_validation` library
5. **Audit Logging**: Standardized logging using `event_logger_lib`
6. **Error Handling**: Robust retry logic with exponential backoff in message processing
7. **FIFO Ordering**: All service bus queues are configured as FIFO to ensure ordering

## Environment Variables

Key environment variables used throughout the platform include:
- SERVICE_BUS_CONNECTION_STRING - For Azure Service Bus connectivity  
- SQL_SERVER, SQL_DATABASE, SQL_USERNAME, MSSQL_SA_PASSWORD - For database connections
- INGRESS_QUEUE_NAME/EGRESS_QUEUE_NAME - Service bus queue configurations 
- HEALTH_CHECK_PORT - For health check endpoints
- WORKFLOW_ID, MICROSERVICE_ID - For audit logging and identification

## Troubleshooting

When working with local development:
1. Ensure Docker Desktop is running
2. Run `just secrets` to generate required secrets 
3. For macOS with Apple Silicon, ensure Docker is configured for x86 emulation
4. Check that all services are connected to the same Docker network
5. Review logs with `just logs` for detailed error information

## Repository Structure Reference

```
integration-hub-beta/
├── README.md                    # Main documentation  
├── TRAINING.md                  # Comprehensive training documentation
├── local/                       # Local development environment  
│   ├── README.md                # Local setup documentation
│   └── justfile                 # Development commands
├── shared_libs/                 # Shared libraries used across services
│   ├── event_logger_lib/
│   ├── field_utils_lib/ 
│   ├── health_check_lib/
│   ├── hl7_validation/
│   ├── message_bus_lib/
│   ├── metric_sender_lib/
│   ├── processor_manager_lib/ 
│   └── transformer_base_lib/
├── hl7_server/                  # HL7 server services
├── transformers/
│   ├── hl7_phw_transformer/
│   ├── hl7_chemo_transformer/
│   ├── hl7_pims_transformer/
│   └── xml_fhir_proms_transformer/
├── hl7_sender/ 
└── message_replay_job/          # Message replay job service
```