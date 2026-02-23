from core.hardware.sx1508 import SX1508, SX1508_GPIO_MODE
import time


def main():
    sx = SX1508()

    sx.configureGPIO(gpio=3, mode=SX1508_GPIO_MODE.OUTPUT, pullup=False, pulldown=True)

    for _ in range(0, 25):
        sx.toggleGPIO(3)
        a = sx._readReg(0x08)
        print(a)
        time.sleep(1)

    sx.reset()


if __name__ == '__main__':
    main()
