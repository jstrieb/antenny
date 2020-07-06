import socket
import json

UDP_PORT = 31337

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('', UDP_PORT))

while True:
    data = json.loads(sock.recv(10240).decode('utf-8'))
    print(json.dumps(data, indent=2))
