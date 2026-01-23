import time

from device_manager.utils.network import getIP
import device_manager.communication.core.tcp.tcp_host as tcp
import logging

logging.basicConfig(level='DEBUG')


def example_host_ips():
    getIP()


def start_tcp_server():
    ip = getIP()
    server = tcp.TCP_SocketsHandler(address=ip['local'])
    server.start()

    time.sleep(10)
    server.close()
    time.sleep(0.01)


if __name__ == '__main__':
    example_host_ips()
    start_tcp_server()
