import time
from robot.bilbo import BILBO
from core.utils.logging_utils import setLoggerLevel, Logger
from robot.logging.bilbo_sample import BILBO_Sample


def main():
    bilbo = BILBO(reset_stm32=False)
    bilbo.init()
    bilbo.start()

    while True:
        time.sleep(1)


if __name__ == '__main__':
    main()
