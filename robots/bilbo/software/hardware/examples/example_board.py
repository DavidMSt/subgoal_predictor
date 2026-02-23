import time

from hardware.control_board import RobotControl_Board


def example_board():
    board = RobotControl_Board()
    tick = 0

    data = {
        'tick': tick,
        'x': 3,
        'y': 'Hello'
    }

    while True:
        if board.wifi_interface.connected:
            data['tick'] = tick
            board.wifi_interface.sendStreamMessage(data)
            tick = tick + 1
        time.sleep(1)


if __name__ == '__main__':
    example_board()
