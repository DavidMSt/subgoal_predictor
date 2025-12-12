import json
import socket
import time

PORT = 12345
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("", PORT))

print(f"Listening on port {PORT}...")

last_recv_time = None

while True:
    data, addr = sock.recvfrom(1024)
    message = data.decode("utf-8")
    message_dict = json.loads(message)
    now = time.time()

    if last_recv_time:
        interval = (now - last_recv_time) * 1000  # ms
        jitter = abs(interval - 1000)             # deviation from 1s expectation
        print(f"Interval: {interval:.2f} ms | Jitter: {jitter:.2f} ms")
    else:
        print(f"First packet received (Seq)")

    last_recv_time = now