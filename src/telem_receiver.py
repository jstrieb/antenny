import socket
import json
import threading

class TelemReceiver:
    """Receive data packets from antenny over UDP and deserialize them from
    JSON into Python objects when received.
    """
    def __init__(self, port: int):
        self.buffer_size = 10240
        self.port = port
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Set the option below in case another instance using the same port
            # needs to be immediately created. See the very bottom of:
            # https://docs.python.org/3/library/socket.html
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(('', self.port))
        except OSError as e:
            self.sock = None
            raise e

    def __del__(self):
        if self.sock is not None:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.sock.close()

    def get(self):
        """Blocking call to receive data and deserialize it."""
        try:
            return json.loads(self.sock.recv(self.buffer_size).decode('utf-8'))
        except (socket.timeout, OSError):
            return None


class ThreadedTelemReceiver(TelemReceiver):
    """Run a threaded telemetry receiver that gets and stores telemetry data
    for instant retrieval.
    """
    def __init__(self, port: int):
        super().__init__(port)
        self.run_thread = True
        self.data_lock = threading.Lock()
        self.last_data = None
        self.thread = None
        self._start_thread()

    def _start_thread(self):
        if self.thread is not None:
            return
        with self.data_lock:
            self.run_thread = True
        self.thread = threading.Thread(target=self._receive_data)
        self.thread.start()

    def _stop_thread(self):
        with self.data_lock:
            self.run_thread = False
        self.thread.join()
        self.thread = None

    def _restart_thread(self):
        self._stop_thread()
        self._start_thread()

    def _continue_running(self):
        with self.data_lock:
            return self.run_thread

    def _receive_data(self):
        while self._continue_running():
            try:
                data = super().get()
            except (socket.timeout, OSError):
                pass

            if data is not None:
                with self.data_lock:
                    self.last_data = data

    def get(self):
        """Instantly get the last-received telemetry data."""
        with self.data_lock:
            return self.last_data


if __name__ == "__main__":
    import time

    telem_receiver = TelemReceiver(31337)
    print("Receiving data...")
    for _ in range(1):
        print(json.dumps(telem_receiver.get(), indent=2))

    print("Receiving data asynchronously...")
    telem_receiver = ThreadedTelemReceiver(31337)
    while True:
        print(json.dumps(telem_receiver.get(), indent=2))
        time.sleep(1)
