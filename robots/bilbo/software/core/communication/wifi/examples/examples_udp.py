import sys
import time
import logging

from core.communication.wifi.udp.udp_socket import UDP_Socket, UDP_Message

logging.basicConfig(level='DEBUG')


def example_udp_receive():
    def rx_callback(message: UDP_Message):
        print(f"Received {message.data.decode('utf-8')} from {message.address}")
        socket.close()
        sys.exit()

    socket = UDP_Socket()
    socket.callbacks.register('rx', rx_callback)

    socket.start()

    while socket.open:
        time.sleep(1)


if __name__ == '__main__':
    example_udp_receive()
