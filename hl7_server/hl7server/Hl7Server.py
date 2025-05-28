import logging

from hl7apy.mllp import MLLPServer

from hl7server.GenericHandler import GenericHandler

class Hl7Server:
    _host: str
    _port: int
    _server: MLLPServer

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port

    def run(self) -> None:

        handlers = {"ADT^A31^ADT_A05": (GenericHandler,)}

        logging.info(f"Starting MLLP server on {self._host}:{self._port}")
        self._server = MLLPServer(self._host, self._port, handlers)

        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            logging.info("Stoping MLLP Server - interrupted")
