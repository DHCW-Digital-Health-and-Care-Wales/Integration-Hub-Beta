import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=False)

# Azure credentials
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")
AZURE_SUBSCRIPTION_ID = os.getenv("AZURE_SUBSCRIPTION_ID", "")

# Application Insights resource ID — used to scope Log Analytics KQL queries to this
# environment only (important when multiple environments share one workspace).
AZURE_APP_INSIGHTS_RESOURCE_ID = os.getenv("AZURE_APP_INSIGHTS_RESOURCE_ID", "")

# Azure Service Bus
AZURE_RESOURCE_GROUP = os.getenv("AZURE_RESOURCE_GROUP", "")
AZURE_SERVICE_BUS_NAMESPACE = os.getenv("AZURE_SERVICE_BUS_NAMESPACE", "")

# Azure Cosmos DB — persistence for alarm configuration and runtime state.
# Locally this points at the Cosmos DB emulator; in cloud environments it points at
# the provisioned Cosmos account. When COSMOS_ENDPOINT is empty the dashboard degrades
# gracefully (alarm config/state simply read back empty).
COSMOS_ENDPOINT = os.getenv("COSMOS_ENDPOINT", "")
# Account key. When set (e.g. the emulator's well-known key) key-based auth is used;
# when empty the shared Azure credential (Managed Identity / service principal) is used
# for data-plane RBAC against the Cosmos account.
COSMOS_KEY = os.getenv("COSMOS_KEY", "")
COSMOS_DATABASE = os.getenv("COSMOS_DATABASE", "integration-hub")
COSMOS_CONTAINER = os.getenv("COSMOS_CONTAINER", "alarms")
# Disable TLS verification — required for the local Cosmos emulator's self-signed
# certificate. Must never be enabled against a real Cosmos account.
COSMOS_DISABLE_SSL_VERIFY = os.getenv("COSMOS_DISABLE_SSL_VERIFY", "false").lower() == "true"

# Environment label derived from AZURE_RESOURCE_GROUP.
# Pattern: UK-South-DHCW-IntHub-{ENV}-App-RG → extracts {ENV} (e.g. TST, DEV, PRD).
# Returns empty string if the RG value is absent or doesn't match the expected pattern.
_raw_environment: str = (
    AZURE_RESOURCE_GROUP.split("-IntHub-")[1].split("-")[0].upper() if "-IntHub-" in AZURE_RESOURCE_GROUP else ""
)

# Optional friendly-name mapping for the navbar environment label.
# Set ENVIRONMENT_LABEL_MAP in .env as comma-separated CODE:Label pairs, e.g.:
#   ENVIRONMENT_LABEL_MAP=TST:TESTING,PRD:PRODUCTION,PPD:PRE-PROD
# Any code not listed falls back to the raw value extracted from AZURE_RESOURCE_GROUP.
_label_map_raw = os.getenv("ENVIRONMENT_LABEL_MAP", "")
ENVIRONMENT_LABEL_MAP: dict[str, str] = {
    k.strip().upper(): v.strip() for pair in _label_map_raw.split(",") if ":" in pair for k, v in (pair.split(":", 1),)
}

ENVIRONMENT_LABEL: str = ENVIRONMENT_LABEL_MAP.get(_raw_environment, _raw_environment)

# Colour name → hex lookup for the environment indicator dot in the navbar.
# Uses the project's established accent palette. Raw hex values (e.g. #ff0000) are
# also accepted directly in ENVIRONMENT_COLOR_MAP and will pass through unchanged.
_COLOUR_NAMES: dict[str, str] = {
    "green": "#22c55e",
    "red": "#ef4444",
    "amber": "#f59e0b",
    "orange": "#f59e0b",
    "purple": "#a855f7",
    "blue": "#3b82f6",
    "cyan": "#06b6d4",
    "teal": "#14b8a6",
    "yellow": "#facc15",
    "white": "#f1f5f9",
    "grey": "#94a3b8",
    "gray": "#94a3b8",
}

# Default colours per environment code — used when no ENVIRONMENT_COLOR_MAP entry exists.
_ENVIRONMENT_COLOR_DEFAULTS: dict[str, str] = {
    "DEV": "green",
    "TST": "purple",
    "UAT": "amber",
    "DTE": "green",
    "LOAD": "cyan",
    "PPD": "red",
    "PRD": "red",
    "DR": "amber",
}

# Optional per-environment colour overrides.
# Set ENVIRONMENT_COLOR_MAP in .env as comma-separated CODE:colourname pairs, e.g.:
#   ENVIRONMENT_COLOR_MAP=TST:purple,PRD:red,DEV:green
# Use colour names from the list above, or a raw hex value (e.g. TST:#c026d3).
# Any code not listed falls back to the built-in defaults above.
_color_map_raw = os.getenv("ENVIRONMENT_COLOR_MAP", "")
_color_map_overrides: dict[str, str] = {
    k.strip().upper(): v.strip() for pair in _color_map_raw.split(",") if ":" in pair for k, v in (pair.split(":", 1),)
}


def _resolve_colour(name: str) -> str:
    """Convert a colour name or raw hex string to a hex colour value."""
    stripped = name.strip().lower()
    if stripped.startswith("#"):
        return stripped
    return _COLOUR_NAMES.get(stripped, "#94a3b8")  # fallback: muted grey


_env_colour_name: str = _color_map_overrides.get(
    _raw_environment,
    _ENVIRONMENT_COLOR_DEFAULTS.get(_raw_environment, "grey"),
)
ENVIRONMENT_COLOR: str = _resolve_colour(_env_colour_name)

# Azure Log Analytics
AZURE_LOG_ANALYTICS_WORKSPACE_ID = os.getenv("AZURE_LOG_ANALYTICS_WORKSPACE_ID", "")

# Azure Container Apps
AZURE_CONTAINER_APPS_ENVIRONMENT = os.getenv("AZURE_CONTAINER_APPS_ENVIRONMENT", "")
AZURE_CONTAINER_APPS_RESOURCE_GROUP = os.getenv("AZURE_CONTAINER_APPS_RESOURCE_GROUP", AZURE_RESOURCE_GROUP)

# Flask
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-in-production")
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

# Alert thresholds
QUEUE_WARNING_THRESHOLD = int(os.getenv("QUEUE_WARNING_THRESHOLD", "10"))
QUEUE_CRITICAL_THRESHOLD = int(os.getenv("QUEUE_CRITICAL_THRESHOLD", "50"))
DLQ_WARNING_THRESHOLD = int(os.getenv("DLQ_WARNING_THRESHOLD", "1"))

# Cache TTL in seconds for /api/status
API_CACHE_TTL = int(os.getenv("API_CACHE_TTL", "30"))

# Demo / simulation mode — returns synthetic data, no Azure credentials needed
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"

# Language — "en" (English) or "cy" (Welsh / Cymraeg)
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "en")
ALERT_EMAIL_ENABLED = os.getenv("ALERT_EMAIL_ENABLED", "false").lower() == "true"
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "")
ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", "")
ACS_CONNECTION_STRING = os.getenv("ACS_CONNECTION_STRING", "")

# UI
SPLASH_SCREEN_ENABLED = os.getenv("SPLASH_SCREEN_ENABLED", "true").lower() == "true"
