import time

from robot.bilbo import BILBO


def main():
    bilbo = BILBO(reset_stm32=False)
    bilbo.init()
    bilbo.start()

    while True:
        time.sleep(100)


if __name__ == '__main__':
    main()
