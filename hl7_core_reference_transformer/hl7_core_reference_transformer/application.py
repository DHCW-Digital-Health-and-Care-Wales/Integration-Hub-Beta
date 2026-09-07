import logging
import os

from .core_reference_transformer import CoreReferenceTransformer

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "ERROR").upper())
azure_log_level_str = os.environ.get("AZURE_LOG_LEVEL", "WARN").upper()
azure_log_level = getattr(logging, azure_log_level_str, logging.WARN)
logging.getLogger("azure").setLevel(azure_log_level)
logger = logging.getLogger(__name__)


def main() -> None:
    transformer = CoreReferenceTransformer()
    transformer.run()


if __name__ == "__main__":
    main()
