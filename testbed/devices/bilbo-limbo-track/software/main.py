import time

from display import TestbedDisplay
from neopixel_bar import HeightIndicator


def main():
    # Start the height indicator
    height_indicator = HeightIndicator()
    height_indicator.start()

    # Start the display
    display = TestbedDisplay()
    display.init()
    display.start()


    while True:
        time.sleep(1)

if __name__ == '__main__':
    main()