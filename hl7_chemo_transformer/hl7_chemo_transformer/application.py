import logging
import os

from .chemocare_transformer import ChemocareTransformer

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "ERROR").upper())
logger = logging.getLogger(__name__)


def main() -> None:
    transformer = ChemocareTransformer()
    transformer.run()


if __name__ == "__main__":
    main()
