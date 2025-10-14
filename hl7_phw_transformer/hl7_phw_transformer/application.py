import logging
import os

from .phw_transformer import PhwTransformer

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "ERROR").upper())
logger = logging.getLogger(__name__)


def main() -> None:
    transformer = PhwTransformer()
    transformer.run()


if __name__ == "__main__":
    main()
