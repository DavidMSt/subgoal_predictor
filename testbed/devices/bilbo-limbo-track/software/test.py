import os
import threading
import time

from display import TestbedDisplay


def run_display_test(display: TestbedDisplay | None = None):
    """
    Simple visual test sequence for the TestbedDisplay.
    Each step waits a few seconds so you can see it.
    """

    if display is None:
        display = TestbedDisplay()

    display.init()

    def test_task():
        print("[Test] Starting display test...")
        time.sleep(3)

        # 1) Basic text + title
        display.set_background_color((0, 0, 0))
        display.set_title("Testbed Display", color=(200, 200, 200))
        display.set_text("Hello World", size=140, color=(255, 255, 255))
        time.sleep(3)

        # 2) Change colors + alignment
        display.set_background_color((20, 20, 80))
        display.set_text("Left aligned", size=120, color=(255, 200, 0), alignment="left")
        display.set_title("Alignment Test", color=(0, 255, 255), alignment="right")
        time.sleep(3)

        # 3) Emoji / icon test
        display.clear()
        display.set_background_color((0, 0, 0))
        display.set_title("Icon Test")
        display.set_icon("🚀", size=200)
        display.set_text("Launching…", size=120)
        time.sleep(3)

        # 4) Clock overlay
        display.clear()
        display.set_title("Clock Overlay")
        display.set_text("Elapsed time", size=120)
        display.set_clock_color((0, 255, 0))
        display.start_clock(mode="overlay")
        time.sleep(5)
        display.stop_clock()

        # 5) Clock replace-text mode
        display.clear()
        display.set_title("Clock Replace Text")
        display.set_clock_color((255, 255, 0))
        display.start_clock(mode="replace_text")
        time.sleep(5)
        display.stop_clock()

        # 6) Background image (if you have one)
        # Change path to an existing image or comment this out
        image_path = "/home/admin/software/bilbolab_logo.png"
        if os.path.isfile(image_path):
            display.clear()
            display.set_title("Image Test", color=(255, 255, 255))
            display.set_image(image_path)
            display.set_text("PNG with transparency", size=100)
            time.sleep(4)

        # 7) Final screen
        display.clear()
        display.set_background_color((0, 0, 0))
        display.set_text("Test complete ✔", size=140, color=(0, 255, 0))
        time.sleep(3)

        print("[Test] Display test finished.")

    thread = threading.Thread(target=test_task, daemon=True)
    thread.start()

    display.start()






if __name__ == '__main__':
    run_display_test()