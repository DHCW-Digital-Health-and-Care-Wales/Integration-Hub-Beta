import os

FLOWS_JSON_PATH: str = os.getenv("FLOWS_JSON_PATH", "flows.json")
SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-prod")
APP_VERSION: str = "0.1.0"
