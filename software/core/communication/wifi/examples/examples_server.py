import time
import logging

from device_manager.communication import addresses
from device_manager.communication.protocols.tcp.tcp_json_protocol import TCP_JSON_Message
from device_manager.communication.tcp_server import TCP_Server
from device_manager.utils.utils import waitForKeyboardInterrupt

logging.basicConfig(level='DEBUG')

device = None


def device_connected_cb(d):
    global device
    device = d


def device_disconnected_cb(d):
    global device
    if device == d:
        device = None


def example_simple_server():
    global device
    server = TCP_Server()
    server.registerCallback('connected', device_connected_cb)
    server.registerCallback('disconnected', device_disconnected_cb)
    server.start()

    while True:
        if device is not None:
            print(server.connections[0].sent)
            msg = TCP_JSON_Message()
            msg.source = 'server'
            msg.address = 'aaa'
            msg.data = {
                'x': 3
            }
            msg.function = 'write'

            server.send(msg, device)
            time.sleep(1)

    waitForKeyboardInterrupt()

    server.close()


if __name__ == '__main__':
    example_simple_server()
