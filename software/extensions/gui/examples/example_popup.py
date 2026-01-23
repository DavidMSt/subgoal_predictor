import time

from core.utils.colors import random_color_from_palette
from core.utils.network.network import getHostIP
from extensions.cli.cli import CommandSet, CLI, Command
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.objects.python.popup import Popup


def example_popup():
    host = getHostIP()
    app = GUI(id="gui", host=host, run_js=True)

    # Category / page
    category = Category(id="widgets", name="Widgets", icon="🤖")
    app.addCategory(category)

    page = Page(id="popup_demo", name="Page")
    category.addPage(page, position=1)

    def create_window_popup(*args, **kwargs, ):
        window_popup = Popup(id='window_popup', type='window', closeable=True, size=[600, 400])
        window_popupbtn1 = Button(widget_id='window_popupbtn1', text='Close',
                                  config={'color': random_color_from_palette('dark')})
        window_popup.group.addWidget(window_popupbtn1, row=1, column=1, width=3, height=2)
        window_popupbtn1.callbacks.click.register(
            lambda *args, **kwargs: window_popup.close())
        window_popupbtn1.callbacks.click.register(
            lambda *args, **kwargs: print("bvhjfdbvjhbdfjkhvbsdfkjhvbhdskjfvbhjdfsbvkjhdfsbvhjkdsf"))
        app.openPopup(window_popup)

    test_button = Button(widget_id='test_button', text='Open Window')
    page.addWidget(test_button, width=4, height=2)
    test_button.callbacks.click.register(create_window_popup)

    cli = CLI('test_cli')
    commandset = CommandSet("TEST")
    cli.root = commandset

    app.cli_terminal.cli = cli

    command = Command(
        name='popup',
        function=create_window_popup,
    )

    commandset.addCommand(command)


    app.start()

    while True:
        time.sleep(1)


if __name__ == '__main__':
    example_popup()
