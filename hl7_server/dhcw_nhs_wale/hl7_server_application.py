import socket
import signal
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MLLP framing characters
MLLP_START = b'\x0b'  # VT
MLLP_END = b'\x1c'  # FS
CARRIAGE_RETURN = b'\x0d'  # CR

REMOTE_HOST = 'inseprodphwdemographics.cymru.nhs.uk'
REMOTE_PORT = 20001


class Hl7ServerApplication:

    def __init__(self):
        self.terminated = False
        signal.signal(signal.SIGINT, lambda signal, frame: self._signal_handler())

    def _signal_handler(self):
        logger.info("\nShutting down server gracefully...")
        self.terminated = True

    def handle_client(self, connection):
        buffer = b''
        while not self.terminated:
            try:
                data = connection.recv(4096)
                if not data:
                    break
                buffer += data

                while MLLP_START in buffer and MLLP_END in buffer:
                    start = buffer.find(MLLP_START)
                    end = buffer.find(MLLP_END)
                    if end < start:
                        buffer = buffer[end + 1:]
                        continue

                    raw_message = buffer[start + 1:end]

                    logger.info("Received HL7 message:\n")

                    hl7_response = self.handle_hl7_message(raw_message)
                    ack = MLLP_START + hl7_response + MLLP_END + CARRIAGE_RETURN
                    connection.sendall(ack)

                    buffer = buffer[end + 2:]  # skip end + CR
            except Exception as e:
                logger.error(f"Error handling client: {e}")
                break

    def start_server(self,host=REMOTE_HOST, port=REMOTE_PORT):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((host, port))
            server_socket.listen(1)
            logger.info(f"MLLP Server listening on {host}:{port}")

            while not self.terminated:
                try:
                    server_socket.settimeout(1.0)  # Timeout to check termination flag
                    conn, addr = server_socket.accept()
                    with conn:
                        logger.info(f"Connected by {addr}")
                        self.handle_client(conn)
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Server error: {e}")

    def handle_hl7_message(self, hl7_data):
        message = hl7_data.decode('utf-8', errors='ignore')
        # You can parse with hl7apy or process as needed
        return b'ACK'




if __name__ == '__main__':
    app = Hl7ServerApplication()
    app.start()
