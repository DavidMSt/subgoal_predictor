import random
import time

from robot.utilities.display.display import Display
from robot.utilities.display.pages import StatusPage


def main():
    display = Display(fps=60)
    status_page = StatusPage()
    display.add_page(status_page)

    display.start()
    time.sleep(1)
    display.change_page('Status')

    status_page.set_battery(level='empty', voltage=0.0)

    time.sleep(1)
    display.displayText(f"HALLO {random.randint(10, 20)}")
    time.sleep(1)
    display.displayText(f"HALLO {random.randint(10, 20)}")
    time.sleep(1)
    display.change_page('Status')
    # for i in range(0, 5):
    #     display.displayText(f"HALLO {random.randint(10, 20)}")
    #     time.sleep(1)

    while True:
        time.sleep(1)


if __name__ == '__main__':
    main()
