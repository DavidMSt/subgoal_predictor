import socket
import time

from core.utils.logging_utils import Logger
from core.utils.time import measure_time
from core.utils.timecode.timecode import Timecode
from hardware.control_board import RobotControl_Board

UDP_IP = "0.0.0.0"  # listen on all interfaces
UDP_PORT = 5005
TC_FPS = 25.0

logger = Logger("UDP Timecode Listener")

def example_timecode_listener():

    board = RobotControl_Board()
    state = True
    board.setStatusLed(state)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", 5005))

    print(f"Listening on port {5005}...")

    while True:
        data, addr = sock.recvfrom(1024)

        state = not state
        with measure_time('setled'):
            board.setStatusLed(state)
        timecode = Timecode.from_bytes(data)
        logger.info(f"Timecode: {timecode}")


if __name__ == '__main__':
    example_timecode_listener()
