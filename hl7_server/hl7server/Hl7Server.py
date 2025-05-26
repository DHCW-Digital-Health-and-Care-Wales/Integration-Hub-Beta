from hl7apy.mllp import MLLPServer

from hl7server.GenericHandler import GenericHandler


class Hl7Server:
    # TODO configure port and host
    _server: MLLPServer

    def run(self) -> None:
        handlers = {"ADT^A31^ADT_A05": (GenericHandler,)}

        self._server = MLLPServer("localhost", 2575, handlers)
        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            pass
