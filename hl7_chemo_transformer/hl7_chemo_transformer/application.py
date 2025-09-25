import logging
import os

from hl7apy.core import Message
from transformer_base_lib import BaseTransformer

from .chemocare_transformer import transform_chemocare_message

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "ERROR").upper())
logger = logging.getLogger(__name__)


class ChemocareTransformer(BaseTransformer):

    def __init__(self) -> None:
        config_path = os.path.join(os.path.dirname(__file__), "config.ini")
        super().__init__("Chemocare", config_path)

    def transform_message(self, hl7_msg: Message) -> Message:
        return transform_chemocare_message(hl7_msg)


def main() -> None:
    transformer = ChemocareTransformer()
    transformer.run()


if __name__ == "__main__":
    main()
