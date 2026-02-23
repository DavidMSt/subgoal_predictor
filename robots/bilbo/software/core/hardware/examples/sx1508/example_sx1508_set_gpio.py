from _archive.cm4_core_old2.hardware.sx1508 import SX1508, SX1508_GPIO_MODE
import time


def main():
    sx = SX1508()

    sx.configureGPIO(gpio=3, mode=SX1508_GPIO_MODE.OUTPUT, pullup=False, pulldown=True)

    sx.writeGPIO(3, 0)
    time.sleep(0.25)
    b = sx._readReg(0x08)
    print(f"{bin(b)}")

    time.sleep(1)

    sx.reset()


if __name__ == '__main__':
    main()
