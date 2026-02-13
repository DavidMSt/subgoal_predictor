import time

from extensions.gui.src.gui import GUI, Category, Page
from core.utils.network.network import getHostIP
from extensions.gui.src.lib.objects.python.camera import CameraWidget


def main():
    host = getHostIP()
    app = GUI(id="gui", host=host, run_js=True)

    # Category / page
    category = Category(id="widgets", name="Widgets", icon="🤖")
    app.addCategory(category)

    page = Page(id="camera_demo", name="Camera")
    category.addPage(page, position=1)

    # ------------------------------------------------------------------------------------------------------------------
    # Camera widget: auto-discovers cameras and streams the first one
    camera = CameraWidget(
        widget_id='camera_widget',
        auto_start=True,
        width=1280,
        height=720,
        fps=30,
        max_scan_index=5,
    )

    page.addWidget(camera, width=2, height=2)

    app.start()

    # Keep alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        camera.close()


if __name__ == "__main__":
    main()
