import logging
import os
import sys

from .app_config import AppConfig
from .message_replay_job import MessageReplayJob

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "ERROR").upper())
azure_log_level_str = os.environ.get("AZURE_LOG_LEVEL", "WARN").upper()
azure_log_level = getattr(logging, azure_log_level_str, logging.WARN)
logging.getLogger("azure").setLevel(azure_log_level)
logger = logging.getLogger(__name__)


def main() -> None:
    try:
        config = AppConfig.read_env_config()
        logger.info("Starting message replay job for batch: %s", config.replay_batch_id)
        job = MessageReplayJob(config)
        job.run()
        logger.info("Message replay job completed successfully")
        sys.exit(0)
    except Exception:
        logger.exception("Message replay job failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
