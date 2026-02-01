import time

from core.communication.wifi.udp.protocols.udp_json_protocol import UDP_JSON_Message
from core.communication.wifi.udp.udp import UDP
from core.communication.wifi.udp.udp_socket import UDP_Socket
import logging

logging.basicConfig(level='DEBUG')


def example_udp_1():
    print("START EXAMPLE 1")

    def rxCallback(message: UDP_JSON_Message, *args, **kwargs):
        print(f"I got a message from {message.meta['source']}.")

    udp = UDP(port=37020)
    udp.init()
    udp.callbacks.register('rx', rxCallback)
    udp.start()

    while True:
        message = UDP_JSON_Message()
        message.type = 'event'
        message.event = 'stop'
        message.data = {
            'a': 5
        }
        # udp.send(message, address='<broadcast>')

        time.sleep(1)


def example_udp_2():
    print("START EXAMPLE 2")
    udp = UDP_Socket_Old()
    udp.init()
    udp.start()

    while True:
        time.sleep(1)


def example_udp_3():
    print("START EXAMPLE 3")
    udp = UDP_Socket(address=None, port=37020)
    udp.start()

    while True:
        time.sleep(1)


if __name__ == '__main__':
    example_udp_1()
