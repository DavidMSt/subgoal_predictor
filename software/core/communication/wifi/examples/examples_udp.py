import time

from core.communication.wifi.udp.protocols.udp_base_protocol import UDP_Base_Message
from core.communication.wifi.udp.protocols.udp_json_protocol import UDP_JSON_Message
from core.communication.wifi.udp.udp import UDP, UDP_Broadcast
from core.utils.network import getLocalIP

from core.utils.time import sleep


def example_1():
    udp = UDP(port=37020)

    udp.init()
    udp.start()

    while True:
        message = UDP_Base_Message()
        message.source = getLocalIP()
        message.address = '255.255.255.255'
        message.data = [1, 2, 3, 4, 5]

        udp.send(message, '<broadcast>', port=37020)

        time.sleep(1)


def example_2():
    udp = UDP(port=[37020])
    udp.init()

    def rxCallback(message: UDP_JSON_Message, *args, **kwargs):
        print(f"I got a message from {message.meta['source']}:{message.meta['port']}")

    udp.registerCallback('rx', rxCallback, port=37020)

    udp.start()

    while True:
        message = UDP_JSON_Message()
        message.type = 'event'
        message.event = 'stop'
        message.data = {
            'a': 5
        }
        udp.send(message, address='<broadcast>', port=37020)
        sleep(3)


def example_3():
    udp = UDP(port=[37020])
    udp.init()

    message = UDP_JSON_Message()
    message.type = 'event'
    message.event = 'stop'
    message.data = {
        'a': 3
    }
    broadcast = UDP_Broadcast()
    broadcast.message = message
    broadcast.time = 1
    broadcast.port = 37020

    # udp.addBroadcast(broadcast)

    udp.start()

    while True:
        udp.send(message)
        time.sleep(1)


if __name__ == '__main__':
    example_2()
