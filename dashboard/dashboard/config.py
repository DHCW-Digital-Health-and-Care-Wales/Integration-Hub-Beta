import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=False)

# Azure credentials
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")
AZURE_SUBSCRIPTION_ID = os.getenv("AZURE_SUBSCRIPTION_ID", "")

# Azure Service Bus
AZURE_RESOURCE_GROUP = os.getenv("AZURE_RESOURCE_GROUP", "")
AZURE_SERVICE_BUS_NAMESPACE = os.getenv("AZURE_SERVICE_BUS_NAMESPACE", "")

# Azure Log Analytics
AZURE_LOG_ANALYTICS_WORKSPACE_ID = os.getenv("AZURE_LOG_ANALYTICS_WORKSPACE_ID", "")

# Azure Container Apps
AZURE_CONTAINER_APPS_ENVIRONMENT = os.getenv("AZURE_CONTAINER_APPS_ENVIRONMENT", "")
AZURE_CONTAINER_APPS_RESOURCE_GROUP = os.getenv(
    "AZURE_CONTAINER_APPS_RESOURCE_GROUP", AZURE_RESOURCE_GROUP
)

# Flask
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-in-production")
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

# Alert thresholds
QUEUE_WARNING_THRESHOLD = int(os.getenv("QUEUE_WARNING_THRESHOLD", "10"))
QUEUE_CRITICAL_THRESHOLD = int(os.getenv("QUEUE_CRITICAL_THRESHOLD", "50"))
DLQ_WARNING_THRESHOLD = int(os.getenv("DLQ_WARNING_THRESHOLD", "1"))

# Cache TTL in seconds for /api/status
API_CACHE_TTL = int(os.getenv("API_CACHE_TTL", "30"))

# Alarm 1 — email notifications (Azure Communication Services)
ALERT_EMAIL_ENABLED = os.getenv("ALERT_EMAIL_ENABLED", "false").lower() == "true"
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "")
ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", "")
ACS_CONNECTION_STRING = os.getenv("ACS_CONNECTION_STRING", "")
