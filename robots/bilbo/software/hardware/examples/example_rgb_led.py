import time

from hardware.control_board import RobotControl_Board
from core.utils.logging_utils import setLoggerLevel

setLoggerLevel('wifi','ERROR')

def main():
    board = RobotControl_Board(device_class='robot', device_type='bilbo', device_revision='v4',
                                        device_id='robot1', device_name='robot1')
    board.init()
    board.start()

    time.sleep(1)
    # board.setRGBLEDExtern([0,100,0])
    board.beep(1000)
    time.sleep(2)
if __name__ == '__main__':
    main()