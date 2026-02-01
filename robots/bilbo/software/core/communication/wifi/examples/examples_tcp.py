import logging
import time

import core.communication.wifi.archive.tcp.tcp as tcp
import core.communication.wifi.udp.udp_socket as udp
from core import utils as network
from core.communication.wifi.archive.tcp import TCP_Handshake_Message, TCP_Handshake_Protocol
from core.communication.wifi.archive.tcp.protocols import TCP_Base_Message
from core.communication.wifi.protocols.tcp import TCP_JSON_Protocol
import core.communication.wifi.archive.addresses as uid

logging.basicConfig(level='DEBUG')


def example_simple_tcp_socket():
    server_address_known = False
    server_address: str = None
    server_port: int = None
    time2 = None
    time1 = None

    def udp_rx_callback(message: udp.UDP_Message):
        nonlocal server_port, server_address, server_address_known

        server_address, server_port = network.splitServerAddress(message.data.decode('utf-8'))
        logging.info(f"Received server info. Address = {server_address}, Port = {server_port}")
        server_address_known = True
        udp_socket.close()

    def tcp_rx_callback(*args, **kwargs):
        ...

    udp_socket = udp.UDP_Socket()
    udp_socket.callbacks.register('rx', udp_rx_callback)
    udp_socket.start()

    while not server_address_known:
        time.sleep(1)

    tcp_socket = tcp.TCP_Socket(server_address=server_address, server_port=server_port)
    tcp_socket.start()

    while not tcp_socket.connected:
        time.sleep(1)

    tcp_socket.callbacks.register('rx', tcp_rx_callback)

    handshake_message = TCP_Handshake_Message()
    handshake_message.protocols = [TCP_JSON_Protocol.identifier]
    handshake_message.name = "TEST"
    handshake_message.uid = [1, 2, 3, 4]

    data = handshake_message.encode()

    msg = TCP_Base_Message()
    msg.data = data
    msg.source = [0, 1]
    msg.address = uid.server
    msg.data_protocol_id = TCP_Handshake_Protocol.identifier
    x = msg.encode()
    tcp_socket.send(x)

    time.sleep(200)

    tcp_socket.close()


if __name__ == '__main__':
    example_simple_tcp_socket()
