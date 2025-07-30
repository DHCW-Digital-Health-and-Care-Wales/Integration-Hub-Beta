# Integration Hub Monitoring Service

This service processes audit events from the Integration Hub and stores them in the monitoring database.

## Configuration

Set the following environment variables:

- `SERVICE_BUS_CONNECTION_STRING`: Azure Service Bus connection string
- `AUDIT_QUEUE_NAME`: Name of the audit queue
- `DATABASE_CONNECTION_STRING`: Database connection string
- `HEALTH_CHECK_HOST`: Health check server hostname
- `HEALTH_CHECK_PORT`: Health check server port

## Database Setup

Run the SQL scripts in the `sql/` directory to create the necessary tables and procedures.
