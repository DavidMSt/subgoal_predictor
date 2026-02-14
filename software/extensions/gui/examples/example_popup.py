import time

from core.utils.colors import random_color_from_palette
from core.utils.network.network import getHostIP
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.objects.python.popup import Popup, YesNoPopup
from extensions.gui.src.lib.objects.python.sliders import SliderWidget
from extensions.gui.src.lib.objects.python.text import TextWidget


def example_popup():
    host = getHostIP()
    app = GUI(id="gui", host=host, run_js=True)

    category = Category(id="popups", name="Popups", icon="🪟")
    app.addCategory(category)

    page = Page(id="popup_demo", name="Popup Demo")
    category.addPage(page, position=1)

    # ── 1. Window popup ──────────────────────────────────────────────────────────
    def open_window_popup(*args, **kwargs):
        popup = Popup(popup_id='window_popup', type='window', title='Window Popup',
                      closeable=True, size=[600, 400], grid=[6, 6])

        label = TextWidget(widget_id='wlabel', text='This is a window popup.\nIt opens in a new browser window.',
                           font_size=11, horizontal_alignment='left', vertical_alignment='top')
        popup.group.addWidget(label, row=1, column=1, width=6, height=3)

        slider = SliderWidget(widget_id='wslider', min_value=0, max_value=100,
                              increment=1, value=50, color=random_color_from_palette('dark'),
                              title='Slider')
        popup.group.addWidget(slider, row=4, column=1, width=4, height=1)

        close_btn = Button(widget_id='wclose', text='Close',
                           color=[0.5, 0.15, 0.15])
        popup.group.addWidget(close_btn, row=6, column=5, width=2, height=1)
        close_btn.callbacks.click.register(lambda *a, **kw: popup.close())

        app.openPopup(popup)

    btn_window = Button(widget_id='btn_window', text='Open Window Popup',
                        color=[0.15, 0.3, 0.5])
    page.addWidget(btn_window, row=1, column=1, width=5, height=2)
    btn_window.callbacks.click.register(open_window_popup)

    # ── 2. Dialog popup ──────────────────────────────────────────────────────────
    def open_dialog_popup(*args, **kwargs):
        popup = Popup(popup_id='dialog_popup', type='dialog', title='Dialog Popup',
                      closeable=True, size=[500, 350], grid=[5, 5])

        label = TextWidget(widget_id='dlabel',
                           text='This is a dialog popup.\nIt opens as an in-page overlay.\nYou can drag, resize, and pop it out.',
                           font_size=11, horizontal_alignment='left', vertical_alignment='top')
        popup.group.addWidget(label, row=1, column=1, width=5, height=2)

        btn_a = Button(widget_id='dbtn_a', text='Option A',
                       color=random_color_from_palette('dark'))
        popup.group.addWidget(btn_a, row=3, column=1, width=2, height=1)
        btn_a.callbacks.click.register(
            lambda *a, **kw: print("Dialog: Option A clicked"))

        btn_b = Button(widget_id='dbtn_b', text='Option B',
                       color=random_color_from_palette('dark'))
        popup.group.addWidget(btn_b, row=3, column=3, width=2, height=1)
        btn_b.callbacks.click.register(
            lambda *a, **kw: print("Dialog: Option B clicked"))

        close_btn = Button(widget_id='dclose', text='Close',
                           color=[0.5, 0.15, 0.15])
        popup.group.addWidget(close_btn, row=5, column=4, width=2, height=1)
        close_btn.callbacks.click.register(lambda *a, **kw: popup.close())

        app.openPopup(popup)

    btn_dialog = Button(widget_id='btn_dialog', text='Open Dialog Popup',
                        color=[0.3, 0.15, 0.5])
    page.addWidget(btn_dialog, row=1, column=7, width=5, height=2)
    btn_dialog.callbacks.click.register(open_dialog_popup)

    # ── 3. Tab popup ─────────────────────────────────────────────────────────────
    def open_tab_popup(*args, **kwargs):
        popup = Popup(popup_id='tab_popup', type='tab', title='Tab Popup',
                      closeable=True, size=[700, 500], grid=[6, 6])

        label = TextWidget(widget_id='tlabel',
                           text='This is a tab popup.\nIt opens in a new browser tab.',
                           font_size=11, horizontal_alignment='left', vertical_alignment='top')
        popup.group.addWidget(label, row=1, column=1, width=6, height=2)

        close_btn = Button(widget_id='tclose', text='Close Tab',
                           color=[0.5, 0.15, 0.15])
        popup.group.addWidget(close_btn, row=6, column=5, width=2, height=1)
        close_btn.callbacks.click.register(lambda *a, **kw: popup.close())

        app.openPopup(popup)

    btn_tab = Button(widget_id='btn_tab', text='Open Tab Popup',
                     color=[0.15, 0.5, 0.3])
    page.addWidget(btn_tab, row=1, column=13, width=5, height=2)
    btn_tab.callbacks.click.register(open_tab_popup)

    # ── 4. Non-closeable dialog ──────────────────────────────────────────────────
    def open_noncloseable_popup(*args, **kwargs):
        popup = Popup(popup_id='nc_popup', type='dialog', title='Non-Closeable Dialog',
                      closeable=False, size=[400, 250], grid=[4, 4])

        label = TextWidget(widget_id='nclabel',
                           text='This dialog has no close button.\nUse the button below to dismiss it.',
                           font_size=11, horizontal_alignment='left', vertical_alignment='top')
        popup.group.addWidget(label, row=1, column=1, width=4, height=2)

        dismiss_btn = Button(widget_id='ncdismiss', text='Dismiss',
                             color=[0.4, 0.4, 0.1])
        popup.group.addWidget(dismiss_btn, row=4, column=2, width=2, height=1)
        dismiss_btn.callbacks.click.register(lambda *a, **kw: popup.close())

        app.openPopup(popup)

    btn_noncloseable = Button(widget_id='btn_noncloseable', text='Non-Closeable Dialog',
                              color=[0.5, 0.4, 0.1])
    page.addWidget(btn_noncloseable, row=4, column=1, width=5, height=2)
    btn_noncloseable.callbacks.click.register(open_noncloseable_popup)

    # ── 5. Large resizable window ────────────────────────────────────────────────
    def open_large_popup(*args, **kwargs):
        popup = Popup(popup_id='large_popup', type='window', title='Large Popup',
                      closeable=True, resizable=True, size=[900, 600], grid=[8, 8])

        label = TextWidget(widget_id='llabel',
                           text='A larger popup with more grid space (8x8).',
                           font_size=11, horizontal_alignment='left', vertical_alignment='top')
        popup.group.addWidget(label, row=1, column=1, width=8, height=1)

        for i in range(1, 7):
            btn = Button(widget_id=f'lbtn_{i}', text=f'Button {i}',
                         color=random_color_from_palette('dark'))
            popup.group.addWidget(btn, row=2 + (i - 1) // 4, column=1 + ((i - 1) % 4) * 2,
                                  width=2, height=1)
            btn.callbacks.click.register(
                lambda *a, idx=i, **kw: print(f"Large popup: Button {idx} clicked"))

        close_btn = Button(widget_id='lclose', text='Close',
                           color=[0.5, 0.15, 0.15])
        popup.group.addWidget(close_btn, row=8, column=7, width=2, height=1)
        close_btn.callbacks.click.register(lambda *a, **kw: popup.close())

        app.openPopup(popup)

    btn_large = Button(widget_id='btn_large', text='Large Window Popup',
                       color=[0.15, 0.35, 0.35])
    page.addWidget(btn_large, row=4, column=7, width=5, height=2)
    btn_large.callbacks.click.register(open_large_popup)

    # ── 6. Dialog without background tint ───────────────────────────────────────
    def open_no_overlay_popup(*args, **kwargs):
        popup = Popup(popup_id='no_overlay_popup', type='dialog', title='No Overlay',
                      closeable=True, size=[450, 300], grid=[5, 5], disable_gui=False)

        label = TextWidget(widget_id='nolabel',
                           text='This dialog does not tint/disable\nthe GUI behind it.',
                           font_size=11, horizontal_alignment='left', vertical_alignment='top')
        popup.group.addWidget(label, row=1, column=1, width=5, height=2)

        close_btn = Button(widget_id='noclose', text='Close',
                           color=[0.5, 0.15, 0.15])
        popup.group.addWidget(close_btn, row=5, column=4, width=2, height=1)
        close_btn.callbacks.click.register(lambda *a, **kw: popup.close())

        app.openPopup(popup)

    btn_no_overlay = Button(widget_id='btn_no_overlay', text='No Background Tint',
                            color=[0.2, 0.35, 0.2])
    page.addWidget(btn_no_overlay, row=7, column=1, width=5, height=2)
    btn_no_overlay.callbacks.click.register(open_no_overlay_popup)

    # ── 7. Semi-transparent dialog ───────────────────────────────────────────────
    def open_transparent_popup(*args, **kwargs):
        popup = Popup(popup_id='transparent_popup', type='dialog', title='Transparent',
                      closeable=True, size=[450, 300], grid=[5, 5],
                      disable_gui=False, opacity=0.7)

        label = TextWidget(widget_id='trlabel',
                           text='This dialog is semi-transparent\n(opacity=0.7) with no overlay.',
                           font_size=11, horizontal_alignment='left', vertical_alignment='top')
        popup.group.addWidget(label, row=1, column=1, width=5, height=2)

        close_btn = Button(widget_id='trclose', text='Close',
                           color=[0.5, 0.15, 0.15])
        popup.group.addWidget(close_btn, row=5, column=4, width=2, height=1)
        close_btn.callbacks.click.register(lambda *a, **kw: popup.close())

        app.openPopup(popup)

    btn_transparent = Button(widget_id='btn_transparent', text='Semi-Transparent',
                             color=[0.35, 0.2, 0.35])
    page.addWidget(btn_transparent, row=7, column=7, width=5, height=2)
    btn_transparent.callbacks.click.register(open_transparent_popup)

    # ── 8. Minimizable dialog ────────────────────────────────────────────────────
    def open_minimizable_popup(*args, **kwargs):
        popup = Popup(popup_id='min_popup', type='dialog', title='Minimizable Dialog',
                      closeable=True, size=[500, 350], grid=[5, 5])

        label = TextWidget(widget_id='mlabel',
                           text='This dialog can be minimized.\nClick the ▁ button in the title bar\nto send it to the dock at the bottom.',
                           font_size=11, horizontal_alignment='left', vertical_alignment='top')
        popup.group.addWidget(label, row=1, column=1, width=5, height=3)

        close_btn = Button(widget_id='mclose', text='Close',
                           color=[0.5, 0.15, 0.15])
        popup.group.addWidget(close_btn, row=5, column=4, width=2, height=1)
        close_btn.callbacks.click.register(lambda *a, **kw: popup.close())

        app.openPopup(popup)

    btn_minimizable = Button(widget_id='btn_minimizable', text='Minimizable Dialog',
                             color=[0.15, 0.4, 0.45])
    page.addWidget(btn_minimizable, row=7, column=13, width=5, height=2)
    btn_minimizable.callbacks.click.register(open_minimizable_popup)

    # ── 9. YesNo popup ───────────────────────────────────────────────────────────
    def open_yesno_popup(*args, **kwargs):
        popup = YesNoPopup(title='Confirm Action', message='Do you want to proceed?')
        popup.yes_button.callbacks.click.register(
            lambda *a, **kw: print("YesNo: User clicked YES"))
        popup.no_button.callbacks.click.register(
            lambda *a, **kw: print("YesNo: User clicked NO"))
        app.openPopup(popup)

    btn_yesno = Button(widget_id='btn_yesno', text='YesNo Popup',
                       color=[0.4, 0.2, 0.1])
    page.addWidget(btn_yesno, row=4, column=13, width=5, height=2)
    btn_yesno.callbacks.click.register(open_yesno_popup)

    # ── Start ────────────────────────────────────────────────────────────────────
    app.start()

    while True:
        time.sleep(1)


if __name__ == '__main__':
    example_popup()
