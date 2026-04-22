import os

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

# Queue name overrides — allows env-based remapping if real names differ
QUEUE_PHW_PRE = os.getenv("QUEUE_PHW_PRE", "pre-phw-transform")
QUEUE_PHW_POST = os.getenv("QUEUE_PHW_POST", "post-phw-transform")
QUEUE_PARIS_PRE = os.getenv("QUEUE_PARIS_PRE", "pre-paris-transform")
QUEUE_PARIS_POST = os.getenv("QUEUE_PARIS_POST", "post-paris-transform")
QUEUE_CHEMO_PRE = os.getenv("QUEUE_CHEMO_PRE", "pre-chemo-transform")
QUEUE_CHEMO_POST = os.getenv("QUEUE_CHEMO_POST", "post-chemo-transform")
QUEUE_PIMS_PRE = os.getenv("QUEUE_PIMS_PRE", "pre-pims-transform")
QUEUE_PIMS_POST = os.getenv("QUEUE_PIMS_POST", "post-pims-transform")
QUEUE_MESSAGE_STORE = os.getenv("QUEUE_MESSAGE_STORE", "message-store")
QUEUE_MPI_OUTBOUND = os.getenv("QUEUE_MPI_OUTBOUND", "mpi-outbound")

# Cache TTL in seconds for /api/status
API_CACHE_TTL = int(os.getenv("API_CACHE_TTL", "30"))
