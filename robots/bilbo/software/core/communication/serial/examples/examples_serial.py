import logging
import time

from core.communication.serial.core.serial_protocol import UART_Message
from core.communication.serial.core.serial_connection import UART_Socket, SerialConnection

logging.basicConfig(
    format='%(asctime)s.%(msecs)03d  %(levelname)-8s  %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')


def example_simple_serial():
    def rx_callback(data, *args, **kwargs):
        logging.info("Received something")

    uart_socket = UART_Socket(device="/dev/ttyAMA1", baudrate=115200)
    uart_socket.callbacks.register('rx', rx_callback)
    uart_socket.start()

    try:
        while True:
            data = bytes([1, 2, 3, 4, 5])

            uart_socket.send(data)
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exit")
        uart_socket.close()


uart: SerialConnection = None


def example_serial_device():
    def rx_callback(message: UART_Message, *args, **kwargs):
        logging.info(f"Receive message with id {message.msg} and cmd {message.cmd} and payload {message.data}")

    global uart
    uart = SerialConnection(device="/dev/ttyAMA1", baudrate=1000000)
    uart.callbacks.register('rx', rx_callback)
    uart.start()

    msg = UART_Message()
    msg.add = [1, 2, 3]
    msg.cmd = 0x01
    msg.flag = 7
    msg.data = [1, 2, 3, 4, 5]

    # for i in range(0, 10):
    #     uart.send(msg)
    #     time.sleep(0.5)
    uart.send(msg)
    time.sleep(1)
    uart.close()
    print("Exit")


if __name__ == '__main__':
    # example_simple_serial()
    example_serial_device()
