import socket
import json

class TelemReceiver:
    """Receive data packets from antenny over UDP and deserialize them from
    JSON into Python objects when received.
    """
    def __init__(self, port: int):
        self.buffer_size = 10240
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('', self.port))

    def get(self):
        """Blocking call to receive data and deserialize it."""
        return json.loads(self.sock.recv(self.buffer_size).decode('utf-8'))
