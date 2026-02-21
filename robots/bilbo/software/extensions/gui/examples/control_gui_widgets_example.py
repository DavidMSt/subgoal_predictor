import math
import random
import threading
import time

import numpy as np

from core.utils.colors import random_color, random_color_from_palette
from core.utils.time import delayed_execution, setInterval, setTimeout, set_timeout
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.map.map import MapWidget
from extensions.gui.src.lib.map.map_objects import Point, Agent, VisionAgent, CoordinateSystem, MapObjectGroup, Line
from extensions.gui.src.lib.objects.objects import Widget_Group, ContextMenuItem, ContextMenuGroup, \
    PagedWidgetGroup, \
    GroupPageWidget, ContainerWrapper, GUI_Container_Stack, GUI_Container, GUI_CollapsibleContainer
from extensions.gui.src.lib.objects.python.bilbo import BILBO_Widget
from extensions.gui.src.lib.objects.python.callout import Callout, CalloutType
from extensions.gui.src.lib.objects.python.checkbox import CheckboxWidget
from extensions.gui.src.lib.objects.python.directory import DirectoryWidget
from extensions.gui.src.lib.objects.python.indicators import CircleIndicator, LoadingIndicator, ProgressIndicator
from extensions.gui.src.lib.objects.python.popup import Popup
from extensions.gui.src.lib.plot.lineplot.lineplot_widget import LinePlotWidget
from extensions.gui.src.lib.plot.realtime.rt_plot import RT_Plot_Widget, TimeSeries, Y_Axis
from extensions.gui.src.lib.objects.python.buttons import Button, MultiStateButton
from extensions.gui.src.lib.objects.python.image import ImageWidget, UpdatableImageWidget
from extensions.gui.src.lib.objects.python.number import DigitalNumberWidget
from extensions.gui.src.lib.objects.python.sliders import SliderWidget, ClassicSliderWidget
from extensions.gui.src.lib.objects.python.select import MultiSelectWidget
from extensions.gui.src.lib.objects.python.dial import RotaryDialWidget
from extensions.gui.src.lib.objects.python.table import Table
from extensions.gui.src.lib.objects.python.text import TextWidget, StatusWidget, StatusWidgetElement
from extensions.gui.src.lib.objects.python.text_input import InputWidget
from core.utils.network.network import getHostIP
from extensions.gui.src.lib.objects.python.video import VideoWidget
from extensions.gui.src.lib.terminal.terminal_widget import TerminalWidget


def main():
    host = getHostIP()
    app = GUI(id='gui', host=host, run_js=True)
    # First category
    category1 = Category(id='widgets',
                         name='Widgets',
                         icon='🤖',
                         )

    app.addCategory(category1)

    # Make the pages
    page_buttons = Page(id='buttons',
                        name='Buttons',
                        )

    page_inputs = Page(id='inputs',
                       name='Inputs', )

    page_data = Page(id='data',
                     name='Data', )

    page_media = Page(id='media',
                      name='Media', )

    page_iframe = Page(id='iframe',
                       name='IFrame', )

    page_groups = Page(id='groups',
                       name='Groups', )

    page_visualization = Page(id='visualization',
                              name='Visualization', )

    page_popups = Page(id='popups',
                       name='Popups', )

    page_misc = Page(id='misc',
                     name='Misc', )

    page_gui_functions = Page(id='gui_functions',
                              name='GUI Functions', )

    category1.addPage(page_inputs, position=1)
    category1.addPage(page_buttons, position=2)
    category1.addPage(page_data)
    category1.addPage(page_media)
    category1.addPage(page_iframe)
    category1.addPage(page_groups)
    category1.addPage(page_visualization)
    category1.addPage(page_popups)
    category1.addPage(page_misc)
    category1.addPage(page_gui_functions)

    subcat1 = Category(id='subcat1',
                       name='Sub 1', )

    subcat1_page1 = Page(id='subcat1_page1',
                         name='Page 1', )
    subcat1.addPage(subcat1_page1)
    category1.addCategory(subcat1)

    subcat2 = Category(id='subcat2',
                       name='Sub 2', )
    subcat2_page1 = Page(id='subcat2_page1',
                         name='Page 2', )
    subcat2.addPage(subcat2_page1)

    button22 = Button(widget_id='button22', text='Button 22', config={})
    subcat2_page1.addWidget(button22, width=3, height=3)
    button22.callbacks.click.register(lambda *args, **kwargs: print(f"Button clicked in subcat2_page1"))
    button22.callbacks.click.register(
        lambda *args, **kwargs: button22.updateConfig(color=[random.random(), random.random(), random.random(), 1], ))

    category1.addCategory(subcat2)

    subcat11 = Category(id='subcat11',
                        name='Sub 11', )
    subcat11_page1 = Page(id='subcat11_page1',
                          name='Page 1-1', )
    subcat11.addPage(subcat11_page1)
    subcat1.addCategory(subcat11)

    # ------------------------------------------------------------------------------------------------------------------
    # Buttons
    button_1 = Button(widget_id='button1', text='Button 1', color=[0.4, 0, 0], )
    page_buttons.addWidget(button_1, width=2, height=2, column=49)

    button_2 = Button(widget_id='button2', text='Color Change', config={'color': [1, 0, 0, 0.2]})
    page_buttons.addWidget(button_2, column=3, width=4, height=4, font_size=20)

    button_2.callbacks.click.register(
        lambda *args, **kwargs: button_2.updateConfig(color=[random.random(), random.random(), random.random(), 1], ))

    button3 = Button(widget_id='button3', text='Small Text', config={'color': "#274D27", 'fontSize': 10})
    page_buttons.addWidget(button3, row=1, column=7, width=4, height=1)

    # Multi-State Button

    def msb_callback(button: MultiStateButton, *args, **kwargs):
        print(f"MSB CLICKED")
        button.increaseIndex()
        new_colors = []
        for color in button.config['color']:
            new_colors.append([random.random(), random.random(), random.random(), 1])
        button.updateConfig(color=new_colors)

    msb1 = MultiStateButton(id='msb1', states=['A', 'B', 'C'], color=['#4D0E11', '#0E4D11', '#110E4D'],
                            config={'fontSize': 16})
    msb1.callbacks.click.register(msb_callback)
    page_buttons.addWidget(msb1, row=2, column=12, width=2, height=2)

    msb2 = MultiStateButton(id='msb2', states=['State 1', 'State 2', 'State 3', 'State 4', 'State 5'],
                            color=[random_color() for _ in range(5)], title='Multi-State Button')

    page_buttons.addWidget(msb2, row=6, column=12, width=4, height=2)

    def reset_button(button, *args, **kwargs):
        if button.state == 'ON':
            delayed_execution(lambda: button.updateConfig(state='OFF'), delay=5)

    msb3 = MultiStateButton(id='msb3', states=['OFF', 'ON'],
                            color=[[0.4, 0, 0], [0, 0.4, 0]], title='Reset')
    msb3.callbacks.state.register(reset_button)
    page_buttons.addWidget(msb3, row=2, column=15, width=2, height=2)

    # ------------------------------------------------------------------------------------------------------------------
    # Sliders
    slider1 = SliderWidget(widget_id='slider1', min_value=0,
                           max_value=1,
                           increment=0.1,
                           value=0.5,
                           color=random_color_from_palette('dark'),
                           continuousUpdates=True,
                           automaticReset=0.5)
    page_inputs.addWidget(slider1, height=2, width=5)

    slider2 = SliderWidget(widget_id='slider2',
                           min_value=0,
                           max_value=100,
                           increment=0.1,
                           value=20,
                           color=random_color_from_palette('dark'),
                           direction='vertical',
                           ticks=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100], )

    page_inputs.addWidget(slider2, height=6, width=2, column=7)

    classic_slider_1 = ClassicSliderWidget(widget_id='cslider1',
                                           value=50,
                                           increment=25,
                                           backgroundColor=random_color_from_palette('dark'),
                                           title_position='left',
                                           valuePosition='right')
    page_inputs.addWidget(classic_slider_1, width=8, height=1, row=8)

    msw1 = MultiSelectWidget(widget_id='msw1',
                             options={
                                 'optionA': {
                                     'label': 'A',
                                     'color': random_color_from_palette('dark'),
                                 },
                                 'optionB': {
                                     'label': 'B',
                                 },
                                 'optionC': {
                                     'label': 'C',
                                     'color': random_color_from_palette('dark'),
                                 }
                             },
                             title='Multi-Select',
                             value='optionA')

    page_inputs.addWidget(msw1, column=11, width=6, height=3)

    msw2 = MultiSelectWidget(widget_id='msw2',
                             options={
                                 'optionA': {
                                     'label': 'Option A',
                                     'color': random_color_from_palette('dark'),
                                 },
                                 'optionB': {
                                     'label': 'Option B',
                                 },
                                 'optionC': {
                                     'label': 'Option C',
                                     'color': random_color_from_palette('dark'),
                                 }
                             },
                             title='Multi-Select',
                             title_position='left',
                             value='optionA')

    page_inputs.addWidget(msw2, column=11, row=5, width=7, height=1)

    dial1 = RotaryDialWidget(widget_id='dial1', value=25, ticks=[0, 25, 50, 75, 100], limitToTicks=True,
                             )

    page_inputs.addWidget(dial1,
                          column=20,
                          width=2,
                          height=3,
                          )

    dial2 = RotaryDialWidget(widget_id='dial2',
                             min_value=0,
                             max_value=1,
                             increment=0.05,
                             title_position='left',
                             value=0.5,
                             continuousUpdates=True,
                             dialColor=random_color_from_palette('pastel'),
                             dialWidth=8,
                             )

    page_inputs.addWidget(dial2, column=20, row=5, width=4, height=3, )

    text_input_1 = InputWidget(widget_id='text_input_1')
    page_inputs.addWidget(text_input_1, row=2, column=27, width=10, height=4)

    text_input_2 = InputWidget(widget_id='text_input_2',
                               title='Test:',
                               title_position='left',
                               color=random_color_from_palette('dark'),
                               datatype='int',
                               value=13,
                               tooltip="Integer",
                               validator=lambda x: x < 20)

    page_inputs.addWidget(text_input_2, row=7, column=27, width=10, height=2)

    text_input_3 = InputWidget(widget_id='text_input_3',
                               title='Input 1:',
                               title_position='left',
                               inputFieldWidth="100px",
                               inputFieldPosition="right", )

    page_inputs.addWidget(text_input_3, row=10, column=27, width=8, height=1)

    text_input_4 = InputWidget(widget_id='text_input_4',
                               title='Input 2:',
                               title_position='left',
                               inputFieldWidth="100px",
                               inputFieldPosition="right",
                               color=random_color_from_palette('dark'), )

    page_inputs.addWidget(text_input_4, row=11, column=27, width=8, height=1)
    text_input_4.setValue("HALLO")

    # Checkbox Widget
    checkbox1 = CheckboxWidget(widget_id='checkbox1', title='Checkbox:', value=False)
    page_inputs.addWidget(checkbox1, row=12, column=1, width=6, height=1)
    checkbox2 = CheckboxWidget(widget_id='checkbox2', title='Checkbox 2:', value=True,
                               checkbox_check_color=[0.9, 0, 0.5, 1])
    page_inputs.addWidget(checkbox2, row=13, column=1, width=6, height=1)

    # ==================================================================================================================
    # Data Page
    dnw1 = DigitalNumberWidget(widget_id='dnw1',
                               title='Theta',
                               value=10,
                               min_value=-1000,
                               max_value=1000,
                               increment=0.001,
                               color='transparent',
                               text_color=random_color_from_palette('pastel'),
                               value_color=[1, 1, 1]
                               )

    page_data.addWidget(dnw1, width=5, height=3)

    text_widget_1 = TextWidget(widget_id='text_widget_1',
                               title='Text Widget',
                               text="Hallo 1 \n13\nThis is a third line",
                               horizontal_alignment='left',
                               vertical_alignment='top',
                               text_color=random_color_from_palette('pastel'),
                               font_weight='bold',
                               font_style='italic', )
    page_data.addWidget(text_widget_1, width=5, height=5)

    status_widget_1 = StatusWidget(widget_id='status_widget_1',
                                   elements={
                                       'el1': StatusWidgetElement(label='Controller',
                                                                  color=[0, 0.5, 0],
                                                                  status='running',
                                                                  ),
                                       'el2': StatusWidgetElement(label='Element 2',
                                                                  color=random_color_from_palette('pastel'),
                                                                  status='Status 2',
                                                                  ),
                                       'el3': StatusWidgetElement(label='Element 3',
                                                                  color=random_color_from_palette('pastel'),
                                                                  status='Status 3',
                                                                  label_color=[1, 1, 1],
                                                                  status_color=[1, 1, 1]),
                                       'el4': StatusWidgetElement(label='Element 4',
                                                                  color=random_color_from_palette('pastel'),
                                                                  status='Status 4',
                                                                  label_color=[1, 1, 1],
                                                                  status_color=[1, 1, 1]),
                                   }
                                   )

    page_data.addWidget(status_widget_1, width=7, height=5)

    table = Table(widget_id="my_table")

    # 2. Register a callback to listen for edits
    #
    # # 3. Add two columns
    # table.addColumn(id="first_name", title="First Name", width=0.5)
    # table.addColumn(id="age", title="Age", width=0.25, type='number', default_value=0, number_increment=0.1,
    #                 text_align='right', )
    # table.addColumn(id="Check", title="Check", width=0.25, type='checkbox', default_value=True, disabled=True)
    # table.addColumn("button", title="Button", width=0.25, type='button', default_value="Click", )
    # table.addColumn("select", title="Select", width=0.25, type='select',
    #                 default_select_options=['', 'Option 1', 'Option 2', 'Option 3'], default_value='', disabled=True)

    def checkInput(input_value):
        print("Checking input:", input_value)
        try:
            value = float(input_value)
            return 0 <= value <= 100
        except ValueError:
            return False

    # # table.addColumn("input", title="Input", width=0.5, type='input', default_value=None, text_align='center',
    # #                 font_family='monospace', input_validator=checkInput)
    # #
    # # # 4. Add some rows (with initial cell values)
    # # row1 = table.addRow(id="row1", cells=["Alice", 30], text_color=[1, 0, 0])
    # #
    # # table.addRow(id="row2", cells=["Bob", 25])
    # # table.addRow(id="row3", cells=["Charlie", 28], text_color=[0, 0, 1])
    # # table.addRow(id="row4", cells=["Diana", 32], text_color=[0, 0.5, 0])
    # # table.addRow(id="row5", cells=["Ethan", 27])
    # # table.addRow(id="row6", cells=["Fiona", 29], text_color=[0.5, 0, 0.5])
    # # table.addRow(id="row7", cells=["George", 35], )
    # # table.addRow(id="row8", cells=["Hannah", 24], text_color=[0.2, 0.2, 0.2])
    # # table.addRow(id="row9", cells=["Ian", 31])
    # # table.addRow(id="row10", cells=["Jenna", 26], text_color=[0, 0.7, 0.7])
    # # row12 = table.addRow(id="row12", cells=["Laura", 22], text_color=[0.3, 0.3, 1])
    # #
    # # def add_kevin():
    # #     table.addRow(id="row11", cells=["Kevin", 33], text_color=[1, 0.5, 0])
    # #
    # # set_timeout(add_kevin, 5)
    # #
    # # c11 = row12.getCell("age")
    # # c11.set(5889)
    # # c11.background_color = [0.5, 0.5, 0.5]
    # # c11.font_family = 'monospace'
    # #
    # # cell_for_select = row12.getCell("select")
    # # cell_for_select.select_options = ['Option 1', 'Option 2', 'Option 3']
    # #
    # # cell_for_check = row12.getCell("Check")
    # # cell_for_check.set(False)
    # #
    # # page_data.addWidget(table, width=25, height=5)
    #
    # # time.sleep(5)
    # cell1 = row1.getCell("button")
    # # cell1.set('Option 2')
    # cell1.callbacks.cell_button_clicked.register(lambda *args, **kwargs: print(f"Button clicked in cell 1"))
    # cell1.set("A")
    # cell1.button_disabled = True
    #
    # cell1.update()

    # ------------------------------------------------------------------------------------------------------------------
    # Plots

    pw1 = RT_Plot_Widget(widget_id="pw1",
                         title='Plot 11',
                         use_local_time=True,
                         x_axis_config={
                             'window_time': 15
                         }
                         )

    y_axis_1 = Y_Axis(id="y_axis_1",
                      label='Axis 1',
                      min=-10,
                      max=10,
                      grid=True
                      )

    pw1.plot.add_y_axis(y_axis_1)
    # pw1.plot.add_y_axis(y_axis_2)

    # setTimeout(lambda: y_axis_2.hide(), 4)

    ds1 = TimeSeries(id="ds1",
                     y_axis="y_axis_1",
                     name='Data 1',
                     color=random_color_from_palette('pastel'))

    pw1.plot.add_timeseries(ds1)

    ds2 = TimeSeries(id="ds2",
                     y_axis="y_axis_1",
                     name='Data 2',
                     color=random_color_from_palette('pastel'))

    pw1.plot.add_timeseries(ds2)

    def test_remove_timeseries():
        pw1.plot.remove_timeseries(ds2)

    setTimeout(test_remove_timeseries, 4)

    page_data.addWidget(pw1, width=20, height=10, row=8)

    # LINEPLOTS
    lineplot1 = LinePlotWidget(widget_id='lineplot1', title='Line Plot 1')
    page_data.addWidget(lineplot1, width=12, height=10)

    # ==================================================================================================================
    # ==================================================================================================================
    # Media Page
    image_widget_1 = ImageWidget(widget_id='image_widget_1',
                                 image='./cat.png')
    image_widget_2 = ImageWidget(widget_id='image_widget_2',
                                 image='./cat.png',
                                 title='Cat Image',
                                 fit='contain',
                                 clickable=True,
                                 background_color=random_color_from_palette('dark'),
                                 )

    page_media.addWidget(image_widget_1, width=5, height=5)
    page_media.addWidget(image_widget_2, width=10, height=5)

    video_widget = VideoWidget(widget_id='video_widget',
                               path='http://frodo1.local:5000/',
                               fit='cover',
                               title='Video Stream',
                               title_color=[1, 1, 1, 0.6], )

    page_media.addWidget(video_widget, width=20, height=12)

    up_image_1 = UpdatableImageWidget(widget_id='up_image_1')
    page_media.addWidget(up_image_1, width=10, height=10)

    x = np.linspace(0, 2 * np.pi, 400)
    y = np.sin(x ** 2)
    #
    # # One-liner: build Agg fig → data-URI → set on widget
    # up_image_1.updateImage(
    #     quick_line_plot_data_uri(
    #         x, y,
    #         figsize=(5, 4), dpi=120,
    #         title="Example: Sine of $x^2$",
    #         xlabel="x", ylabel="sin(x²)",
    #         color="royalblue", label=r"$\sin(x^2)$",
    #     )
    # )

    # ── LIVE PLOT (thread-safe, headless Agg) ─────────────────────────────────────
    # up_image_live2 = UpdatableImageWidget(widget_id='up_image_live2', title="Live (Agg backend)")
    # page_media.addWidget(up_image_live2, width=10, height=10)
    #
    # def live_sine(widget: UpdatableImageWidget, stop_evt: threading.Event, fps: float = 8.0):
    #     # Build a headless (Agg) figure
    #     fig, ax = new_figure_agg(figsize=(5, 4), dpi=120)
    #     x = np.linspace(0, 2 * np.pi, 400)
    #     phase = 0.0
    #     (line,) = ax.plot(x, np.sin(x + phase), lw=2, label="sin(x + phase)")
    #     ax.set_title("Live: sin(x + phase)")
    #     ax.set_xlabel("x")
    #     ax.set_ylabel("Amplitude")
    #     ax.grid(True, alpha=0.3)
    #     ax.legend(loc="upper right")
    #
    #     # Push first frame
    #     up_image_live2.setFromMatplotLib(fig, dpi=120)
    #
    #     def tick():
    #         nonlocal phase
    #         phase += 0.2
    #         line.set_ydata(np.sin(x + phase))
    #         up_image_live2.setFromMatplotLib(fig, dpi=120)
    #
    #     try:
    #         run_periodic(stop_evt.is_set, 1.0 / max(fps, 1e-6), tick)
    #     finally:
    #         safe_close(fig)
    #
    # # Start/stop controls
    # stop_event2 = threading.Event()
    # threading.Thread(target=live_sine, args=(up_image_live2, stop_event2), daemon=True).start()
    #
    # up_image_plotbg = UpdatableImageWidget(
    #     widget_id="up_image_plotbg",
    #     title="Sine Plot with Blue Background",
    #     fit="contain"
    # )
    # page_media.addWidget(up_image_plotbg, width=8, height=8)

    # ── Make the figure with a background color ───────────────────────────────────
    x = np.linspace(0, 2 * np.pi, 400)
    y = np.sin(x)

    # fig, ax = new_figure_agg(figsize=(5, 4), dpi=120)
    # ax.plot(x, y, color="white", lw=2, label="sin(x)")

    # # Set plot backgrounds directly in Matplotlib
    # fig.patch.set_facecolor("#1e1e2f")  # overall figure background
    # ax.set_facecolor("#2e2e4f")  # plotting area background
    #
    # ax.set_title("Dark Plot with Colored Line", color="white")
    # ax.set_xlabel("x", color="white")
    # ax.set_ylabel("sin(x)", color="white")
    # ax.tick_params(colors="white")
    # ax.grid(True, alpha=0.3, color="lightgray")
    # ax.legend(facecolor="#2e2e4f", edgecolor="white", labelcolor="white")
    #
    # # ── Push to the widget ───────────────────────────────────────────────────────
    # up_image_plotbg.updateImage(fig_to_data_uri(fig, dpi=120, transparent=False))
    #
    # save_figure(fig, filepath='/Users/lehmann/Desktop/test2', fmt='pdf', dpi=120)
    # safe_close(fig)

    # ==================================================================================================================
    # Groups Page
    group1 = Widget_Group(group_id='group1',
                          border_width=1,
                          border_color=random_color_from_palette('pastel'),
                          )

    page_groups.addWidget(group1, width=10, height=10, row=5)

    group_button_1 = Button(widget_id='group_button_1', text='GP 1',
                            config={'color': random_color_from_palette('dark')})
    group_slider_1 = SliderWidget(widget_id='group_slider_1',
                                  min_value=0,
                                  max_value=1,
                                  increment=0.1,
                                  value=0.5,
                                  color=random_color_from_palette('dark'),
                                  )

    group1.addWidget(group_button_1, width=2, height=2, row=2, column=4)
    group1.addWidget(group_slider_1, width=6, height=2)

    group_button_1.callbacks.click.register(
        lambda *args, **kwargs: group_button_1.updateConfig(color=random_color_from_palette('dark')))

    group2 = Widget_Group(group_id='group2', columns=3, rows=30, fit=False, show_scrollbar=True, )
    page_groups.addWidget(group2, width=10, height=18)

    group3 = Widget_Group(group_id='group3',
                          title='Group 3',
                          title_color=random_color_from_palette('pastel'),
                          columns=4,
                          rows=12,
                          fit=False,
                          show_scrollbar=True,
                          )

    group2.addWidget(group3, width=3, height=3, row=2)

    group_button_2 = Button(widget_id='group_button_2', text='GP2', color=[0.3, 0, 0])

    group3.addWidget(group_button_2, width=1, height=1)

    # Paged Groups
    page1 = PagedWidgetGroup(group_id='page1', title='Page 1', icon='1')
    page2 = PagedWidgetGroup(group_id='page2', title='Page 2', rows=30, fit=False, show_scrollbar=True, icon='❤️')
    page3 = PagedWidgetGroup(group_id='page3', title='Page 3', icon='3', hidden=False)
    page4 = PagedWidgetGroup(group_id='page4', title='Page 4', icon='4')
    page5 = PagedWidgetGroup(group_id='page5', title='Page 5', icon='5')
    page6 = PagedWidgetGroup(group_id='page6', title='Page 6', icon='6')
    page7 = PagedWidgetGroup(group_id='page7', title='Page 7', icon='7')
    page8 = PagedWidgetGroup(group_id='page8', title='Page 8', icon='8')

    paged_group1 = GroupPageWidget(group_id='paged_group1', group_bar_style='buttons')
    paged_group1.addGroup(page1)
    paged_group1.addGroup(page2)
    paged_group1.addGroup(page3)
    paged_group1.addGroup(page4)
    paged_group1.addGroup(page5)
    paged_group1.addGroup(page6)
    paged_group1.addGroup(page7)
    paged_group1.addGroup(page8)

    tbpg3 = Button(widget_id='tbpg3', text='TBPG3', color=[0.3, 0, 0])
    page3.addWidget(tbpg3, width=2, height=2)

    page_groups.addWidget(paged_group1, width=12, height=16)
    delayed_execution(paged_group1.setGroup, 5, 'page3')

    def add_item_to_page_3(*args, **kwargs):
        button_test = Button(widget_id='tbpg4', text='TBPG4', color=[0.3, 0, 0.3])
        page3.addWidget(button_test, width=2, height=2)
        page3.removeWidget(tbpg3)
        # paged_group1.hideGroupBar()

    delayed_execution(add_item_to_page_3, 7)

    # Collapsible groups
    # cg_container = CollapsibleGroupContainer('cgc1')
    # page_groups.addObject(cg_container, width=18, height=10)

    cw1 = ContainerWrapper('cw1', height_mode='auto')

    # Make a stack
    stack1 = GUI_Container_Stack('stack1')
    cw1.container.addObject(stack1)

    # Make a simple container and add it to the stack
    container1 = GUI_Container('container1', height_mode='fixed', height=200, background_color=[0.3, 0.0, 0.3])

    container2 = GUI_Container('container2', height_mode='fixed', height=200, border_width=1)

    group_in_container_1 = Widget_Group(group_id='group_in_container_1', fit=False, rows=10, columns=10)
    # container2.addObject(group_in_container_1)

    btn885 = Button(widget_id='btn885', text='A', color=[0.3, 0, 0])
    group_in_container_1.addWidget(btn885, width=1, height=1)

    container3 = GUI_CollapsibleContainer('container3', start_collapsed=True, height_mode='auto', height=150)

    stack1.addContainer(container3)
    stack1.addContainer(container2)
    stack1.addContainer(container1)

    # container3.addObject(group_in_container_1)

    stack2 = GUI_Container_Stack('stack2')
    stack2_container1 = GUI_CollapsibleContainer(id='ncvjdfn', title='Collapsible 1', height_mode='auto', height=100)
    stack2_container2 = GUI_CollapsibleContainer(id='vbbfbgf', title='Collapsible 2', height_mode='fixed', height=100)
    stack2.addContainer(stack2_container1)
    stack2.addContainer(stack2_container2)

    container3.addObject(stack2)

    stack2_container1.addObject(table)

    page_groups.addWidget(cw1, width=18, height=10)

    # ==================================================================================================================
    # Visualization Page
    map_widget = MapWidget(widget_id='map_widget', )
    page_visualization.addWidget(map_widget, width=18, height=18)

    point1 = Point('point1', x=0, y=2.5)
    map_widget.map.addObject(point1)

    agent1 = Agent('agent1', x=2, y=1, psi=0.5)
    map_widget.map.addObject(agent1)

    visionAgent1 = VisionAgent('vision_agent1', name='VA2', x=0.5, y=1.5, psi=-1.5, show_trail=True)
    map_widget.map.addObject(visionAgent1)

    cs1 = CoordinateSystem('cs1', x=2, y=0.5, psi=-math.pi / 4, show_name=True)
    map_widget.map.addObject(cs1)

    group1 = MapObjectGroup('group1', visible=True)
    group2 = MapObjectGroup('group2', visible=True)
    group1.addGroup(group2)
    point2 = Point('point2', x=2.2, y=2.2, show_name=False, color=[0, 0.9, 0.4], dim=False)
    group2.addObject(point2)
    map_widget.map.addGroup(group1)

    def test_remove_point():
        group2.removeObject(point2)

    delayed_execution(test_remove_point, 10)

    def update():
        x = visionAgent1.data['x']
        y = visionAgent1.data['y']
        visionAgent1.update(x=x + 0.002, y=y + 0.002, psi=visionAgent1.data['psi'] + 0.02)

    setInterval(update, 0.02)

    line1 = Line('line1', start=point1, end=visionAgent1)
    map_widget.map.addObject(line1)

    # delayed_execution(group2.visible, 10, False)

    def test_add():
        point3 = Point('point3', x=0.5, y=0.5, color=[0, 0.9, 0.2], dim=False)
        map_widget.map.addObject(point3)

        def test_remove():
            map_widget.map.removeObject(point3)

        delayed_execution(test_remove, 5)

    delayed_execution(test_add, 5)
    # ==================================================================================================================
    # Popups and Callouts
    button_popup_open_1 = Button(widget_id='button_popup_open_1', text='Open Dialog')
    page_popups.addWidget(button_popup_open_1, width=4, height=2)

    def create_dialog_popup(*args, **kwargs, ):
        dialog_popup = Popup(id='dialog_popup', type='dialog', closeable=True, size=[400, 300], grid=[4, 4])
        dialog_popupbtn1 = Button(widget_id='dialog_popupbtn1', text='Close',
                                  config={'color': random_color_from_palette('dark')})
        dialog_popup.group.addWidget(dialog_popupbtn1, row=1, column=1, width=2, height=2)
        dialog_popupbtn1.callbacks.click.register(
            lambda *args, **kwargs: dialog_popup.close())

        app.openPopup(dialog_popup)

    button_popup_open_1.callbacks.click.register(create_dialog_popup)

    def create_window_popup(*args, **kwargs, ):
        window_popup = Popup(id='window_popup', type='window', closeable=True, size=[600, 400])
        window_popupbtn1 = Button(widget_id='window_popupbtn1', text='Close',
                                  config={'color': random_color_from_palette('dark')})
        window_popup.group.addWidget(window_popupbtn1, row=1, column=1, width=3, height=2)
        window_popupbtn1.callbacks.click.register(
            lambda *args, **kwargs: window_popup.close())
        window_popupbtn1.callbacks.click.register(lambda *args, **kwargs: print("bvhjfdbvjhbdfjkhvbsdfkjhvbhdskjfvbhjdfsbvkjhdfsbvhjkdsf"))
        app.openPopup(window_popup)

    button_popup_open_2 = Button(widget_id='button_popup_open_2', text='Open Window')
    button_popup_open_2.callbacks.click.register(create_window_popup)
    page_popups.addWidget(button_popup_open_2, width=4, height=2)

    button_callout_1 = Button(widget_id='button_callout_1', text='INFO Callout')
    page_popups.addWidget(button_callout_1, width=4, height=2)

    def create_callout_1(*args, **kwargs, ):
        callout = Callout(title='Info Callout',
                          content='This is an info callout',
                          callout_type=CalloutType.INFO,
                          timeout=10)
        app.callout_handler.add(callout)

    button_callout_1.callbacks.click.register(create_callout_1)

    button_callout_2 = Button(widget_id='button_callout_2', text='WARNING Callout')
    page_popups.addWidget(button_callout_2, width=4, height=2)

    def create_callout_2(*args, **kwargs, ):
        callout = Callout(title='Warning Callout',
                          content='This is a warning callout',
                          callout_type=CalloutType.WARNING,
                          timeout=10)
        app.callout_handler.add(callout)

    button_callout_2.callbacks.click.register(create_callout_2)

    # ==================================================================================================================
    # MISC PAGE
    circle_indicator = CircleIndicator(widget_id='circle_indicator', blinking=True, size=50,
                                       color=random_color_from_palette('pastel'), )
    page_misc.addWidget(circle_indicator, width=2, height=2)

    loading_indicator = LoadingIndicator(widget_id='loading_indicator', diameter=50, speed=1, border=False)
    page_misc.addWidget(loading_indicator, width=2, height=2)

    progress_indicator = ProgressIndicator(widget_id='progress_indicator', value=0.0, title='Progress', label='0%',
                                           border=False)
    page_misc.addWidget(progress_indicator, width=8, height=2)

    directory_widget = DirectoryWidget(widget_id='directory_widget', directory='/Users/lehmann/Desktop/test')
    page_misc.addWidget(directory_widget, width=10, height=10)

    terminal_widget = TerminalWidget(widget_id='terminal_widget', host=host)
    page_misc.addWidget(terminal_widget, width=17, height=17)

    # ==================================================================================================================
    # GUI Functions Page

    gui_function_button_1 = Button(widget_id='gui_function_button_1', text='Execute Function', )
    page_gui_functions.addWidget(gui_function_button_1, width=3, height=3)

    def gui_function_callback(*args, **kwargs):
        app.function(function_name='testFunction', args='Hello from the Backend')

    gui_function_button_1.callbacks.click.register(gui_function_callback)

    contextmenu_button = Button(widget_id='contextmenu_button', text='Context Menu')
    page_gui_functions.addWidget(contextmenu_button, width=3, height=2, row=8)

    test_item = ContextMenuItem(id='test_item', name='Test Item', front_icon='❤️‍🩹', back_icon='🍉')
    contextmenu_button.context_menu.addItem(test_item)
    test_item_2 = ContextMenuItem(id='test_item_2', name='Test Item 2 (Test)', front_icon='', back_icon='🐼')
    contextmenu_button.context_menu.addItem(test_item_2)

    test_group = ContextMenuGroup(id='test_group', name='Test Group', type='submenu')
    test_item_3 = ContextMenuItem(id='test_item_3', name='Test Item 3', front_icon='🐼', back_icon='🐼')
    test_group.addItem(test_item_3)
    test_item_4 = ContextMenuItem(id='test_item_4', name='Test Item 4', front_icon='🐼', back_icon='🐼')
    test_group.addItem(test_item_4)
    second_layer_group = ContextMenuGroup(id='second_layer_group', name='Second Layer Group', type='submenu')
    test_item_5 = ContextMenuItem(id='test_item_5', name='Test Item 5', front_icon='🐼', back_icon='🐼')
    second_layer_group.addItem(test_item_5)
    test_group.addItem(second_layer_group)

    contextmenu_button.context_menu.addItem(test_group)

    bilbo_widget = BILBO_Widget(widget_id='bilbo_widget')
    page_gui_functions.addWidget(bilbo_widget, width=12, height=12, row=3, column=20)

    # ==================================================================================================================

    # ==================================================================================================================

    # ==================================================================================================================
    app.start()

    # time.sleep(5)
    #
    # popup = Popup(id='popup1', type='dialog', closeable=True, )
    # popupbtn1 = Button(id='popupbtn1', text='Close', config={'color': random_color_from_palette('dark')})
    # popup.group.addObject(popupbtn1, row=1, column=1, width=3, height=2)
    # popup.group.config['fill_empty'] = False
    #
    # popupbtn1.callbacks.click.register(
    #     lambda *args, **kwargs: popup.close())
    #
    # popupslider = SliderWidget(widget_id='popup_slider',
    #                            min_value=0,
    #                            max_value=1,
    #                            increment=0.01,
    #                            value=0.5,
    #                            color=random_color_from_palette('dark'),
    #                            title='Popup Slider',
    #                            )
    #
    # popup.group.addObject(popupslider, row=4, column=1, width=4, height=2)
    # app.addPopup(popup)

    # ==================================================================================================================
    i = 0
    while True:
        dnw1.value = random.randint(-1000, 1000) / 100

        ds1.set_value(random.random() * 10 - 5)
        ds2.set_value(random.random() * 10 - 5)
        # dataseries_1.setValue(random.random() * 10 - 5)

        # c11.set(random.randint(0, 10000))

        # progress_indicator.sendUpdate({'value': i % 100 / 100, 'label': f"{i % 100}%"})
        i += 1
        time.sleep(0.1)


if __name__ == '__main__':
    main()
