import logging
import os

from .pims_transformer import PimsTransformer

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "ERROR").upper())
logger = logging.getLogger(__name__)


def main() -> None:
    transformer = PimsTransformer()
    transformer.run()


if __name__ == "__main__":
    main()
