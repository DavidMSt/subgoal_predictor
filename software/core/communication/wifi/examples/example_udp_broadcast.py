import logging
import time

import device_manager.communication.core.udp as udp
import device_manager.utils.network

logging.basicConfig(level='DEBUG')


def example_udp_broadcast():
    ip = device_manager.utils.network.getAllIPAdresses()
    server = udp.UDP_Socket(address=ip['local'], port=44444)
    server.start()

    broadcast = udp.UDP_Broadcast()
    broadcast.data = "6666"
    broadcast.time = 1
    broadcast.port = 37020
    server.addBroadcast(broadcast)

    try:
        time.sleep(30)
    except KeyboardInterrupt:
        ...

    server.close()


if __name__ == '__main__':
    example_udp_broadcast()
