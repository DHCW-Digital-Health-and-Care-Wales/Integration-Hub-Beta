import logging
from os import getenv
from dotenv import load_dotenv

from hl7server.Hl7Server import Hl7Server

load_dotenv(".env")

logging.basicConfig(level=getenv("LOG_LEVEL", "INFO"))

host = getenv("HOST", "localhost")
port = int(getenv("PORT", "2575"))

hl7Server = Hl7Server(host, port)
hl7Server.run()
