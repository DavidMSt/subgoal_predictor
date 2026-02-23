import logging
import time

from core.communication.wifi.archive.wifi_connection import WIFI_Connection

logging.basicConfig(level='DEBUG')


def example_wifi_1():
    wifi = WIFI_Connection(id='c4-02', address=b'\x01\x01', config={'rx_queue': True})

    def testfunction(message):
        nonlocal wifi
        wifi.send(message)
        print(wifi.rx_queue.qsize())

    def connectedfunction():
        print("CONNECTED")

    wifi.callbacks.register('rx', testfunction)
    wifi.callbacks.register('connected', connectedfunction)

    wifi.start()
    time.sleep(100)


if __name__ == '__main__':
    example_wifi_1()
