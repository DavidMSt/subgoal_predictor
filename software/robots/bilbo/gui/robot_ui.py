import math
import time
from typing import Dict

import numpy as np

from core.utils.uuid_utils import generate_uuid
from core.utils.colors import get_palette
from core.utils.lipo import lipo_soc
from core.utils.logging_utils import Logger
from core.utils.time import set_timeout, setInterval
from extensions.gui.src.app import App, Folder, FolderPage
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.map.map import MapWidget
from extensions.gui.src.lib.map.map_objects import Agent, Point, Line, Rectangle, MapObject
from extensions.gui.src.lib.objects.objects import Widget_Group
from extensions.gui.src.lib.objects.python.bilbo_mode import BilboModeWidget
from extensions.gui.src.lib.objects.python.buttons import MultiStateButton, Button
from extensions.gui.src.lib.objects.python.checkbox import CheckboxWidget
from extensions.gui.src.lib.objects.python.dial import RotaryDialWidget
from extensions.gui.src.lib.objects.python.indicators import (
    BatteryIndicatorWidget, ConnectionIndicator, InternetIndicator, JoystickIndicator,
)
from extensions.gui.src.lib.objects.python.joystick import JoystickWidget
from extensions.gui.src.lib.objects.python.number import DigitalNumberWidget
from extensions.gui.src.lib.objects.python.table import Table, TextColumn, TableGroup
from extensions.gui.src.lib.objects.python.text import TextWidget, StatusWidget, StatusWidgetElement
from extensions.gui.src.lib.plot.realtime.rt_plot import TimeSeries, RT_Plot_Widget
from robots.bilbo.gui.applications.dilc_app import DILC_APP
from robots.bilbo.robot.bilbo import BILBO
from robots.bilbo.robot.bilbo_data import BILBO_Sample
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode
from robots.bilbo.robot.bilbo_position_control import MoveToPointCommand, TurnToHeadingCommand, PathData
from robots.bilbo.robot.bilbo_utilities import CONTROL_MODE_COLORS
from robots.bilbo.testbed.objects import BoxObstacle
from robots.bilbo.testbed.testbed_manager import TestbedManager


# ======================================================================================================================
class RobotUI:
    _built: bool = False

    plots: list[RT_Plot_Widget]
    overview_page_data: dict

    _additional_map_objects: list[MapObject] = []

    # === INIT =========================================================================================================
    def __init__(self, robot: BILBO, manager: TestbedManager, gui: GUI, app: App, application_settings):
        self.robot = robot
        self.gui = gui
        self.app = app
        self.manager = manager
        self.application_settings = application_settings

        self.pages: Dict[str, Page] = {}
        self.category = Category(id=robot.id, icon='🤖')
        self.gui.categories['robots'].addCategory(self.category)

        self._additional_map_objects: list[MapObject] = []
        self._obstacle_map_objects: dict[str, MapObject] = {}  # obstacle_id -> map object

        self.folder = Folder(folder_id=robot.id)

        self.robot.core.events.stream.on(self.on_robot_stream)
        if self.manager.tracker is not None:
            self.manager.tracker.events.new_sample.on(self.on_new_tracker_sample, max_rate=20)
        self.logger = Logger(f"Category {self.robot.id}")

        # Register DILC experiment events (via experiment_handler, which owns the event)
        self.robot.experiment_handler.events.dilc_experiment_initialized.on(
            self.on_dilc_experiment_initialized, spawn_new_threads=True)

        self.robot.device.callbacks.disconnected.register(self.close)
        # Handle Mode changes
        self.robot.core.events.control_mode_changed.on(self.on_control_mode_changed)
        self.robot.control.events.tic_mode_changed.on(self.on_tic_mode_changed)
        self.robot.control.events.vic_mode_changed.on(self.on_vic_mode_changed)

        # Build
        self.plots = []
        self.overview_page_data = {}

        self.build()
        self.build_folder()

    # === METHODS ======================================================================================================
    def build(self):
        time.sleep(0.5)
        self.page_overview = Page(id='overview', name='🤖 Overview', icon='🤖')
        self.build_overview_page(self.page_overview)
        self.category.addPage(self.page_overview)
        page_control = Page(id='control', name='🎛️ Control', icon='🎛️')
        self.build_control_page(page_control)
        self.category.addPage(page_control)
        page_debug = Page(id='debug', name='🔧 Debug', icon='🔧')
        self.build_debug_page(page_debug)
        self.category.addPage(page_debug)

        self._built = True

        self.gui.function(
            function_name='setPage',
            args=[self.page_overview.uid]
        )

    # ------------------------------------------------------------------------------------------------------------------
    def build_overview_page(self, page):
        # --- GENERAL GROUP --------------------------------------------------------------------------------------------
        general_group = Widget_Group(group_id='general', title='General', rows=5, columns=11)
        page.addWidget(general_group, row=1, column=1, width=11, height=6)

        self.general_status_widget = StatusWidget(
            widget_id='general_status_widget',
            title='Status',
            elements={
                'status': StatusWidgetElement(label='Status',
                                              color=[0, 0.5, 0],
                                              status='ok',
                                              ),
                'mode': StatusWidgetElement(label='Control Mode',
                                            color=CONTROL_MODE_COLORS[self.robot.control.mode],
                                            status=self.robot.control.mode.name,
                                            ),
                'experiment': StatusWidgetElement(label='Experiment',
                                                  color=[0.5, 0.5, 0.5],
                                                  status='idle',
                                                  )

            }
        )
        general_group.addWidget(self.general_status_widget, row=1, column=1, width=11, height=3)

        # Battery
        self.battery_indicator = BatteryIndicatorWidget(
            widget_id='battery_indicator',
            label_position='center',
            show='voltage',
        )
        general_group.addWidget(self.battery_indicator, row=4, column=9, width=3, height=2)

        # Connection
        self.connection_strength_indicator = ConnectionIndicator(widget_id='connection_strength_indicator')
        general_group.addWidget(self.connection_strength_indicator, row=4, column=1, width=3, height=2)
        #
        # Internet
        self.internet_indicator = InternetIndicator(widget_id='internet_indicator')
        general_group.addWidget(self.internet_indicator, row=4, column=4, width=2, height=2)
        #
        # Joystick indicator + context menu
        self.joystick_indicator = JoystickIndicator(widget_id='joystick_indicator')
        self.joystick_indicator.setValue(False)
        general_group.addWidget(self.joystick_indicator, row=4, column=6, width=3, height=2)

        # # Context menu group
        # joystick_group = ContextMenuGroup(id='joystick_group', name='Joysticks')
        # self.joystick_indicator.context_menu.addItem(joystick_group)
        #
        # # Guard: if joystick control is not provided, stop here
        # if js_control is None:
        #     return
        #
        # self.joystick_contextmenu_items: Dict[str, dict] = {}
        #
        # def _register_item(joystick):
        #     joystick_id = str(joystick.id)
        #     item = ContextMenuItem(id=joystick_id, name=f"{joystick.name} (ID: {joystick_id})")
        #     joystick_group.addItem(item)
        #
        #     # Clicking assigns the joystick to this robot
        #     item.callbacks.click.register(
        #         Callback(function=js_control.assignJoystick, inputs={'joystick': joystick, 'bilbo': self.robot})
        #     )
        #
        #     self.joystick_contextmenu_items[joystick_id] = {
        #         'item': item,
        #         'joystick': joystick,
        #         'assignment': None,
        #     }
        #
        # # Initial population
        # for joystick_id, joystick_data in js_control.getJoysticksWithAssignments().items():
        #     _register_item(joystick_data['joystick'])
        #
        # # Live updates
        # def add_joystick_menu_item(joystick, *args, **kwargs):
        #     _register_item(joystick)
        #
        # def remove_joystick_menu_item(joystick, *args, **kwargs):
        #     jid = str(joystick.id)
        #     if jid in self.joystick_contextmenu_items:
        #         joystick_group.removeItem(self.joystick_contextmenu_items[jid]['item'])
        #         del self.joystick_contextmenu_items[jid]
        #
        # def new_assignment(joystick, robot: BILBO, *args, **kwargs):
        #     self.logger.info(f'New assignment: {joystick.id} -> {robot.id}')
        #     jid = str(joystick.id)
        #     if jid in self.joystick_contextmenu_items:
        #         item = self.joystick_contextmenu_items[jid]
        #         if robot == self.robot:
        #             item['item'].name = f"{item['joystick'].name} (ID: {jid}) ✅"
        #         else:
        #             item['item'].name = f"{item['joystick'].name} (ID: {jid}) (-> {robot.id})"
        #
        # def assignment_removed(joystick, robot: BILBO, *args, **kwargs):
        #     self.logger.info(f'Assignment removed: {joystick.id} -> {robot.id}')
        #     jid = str(joystick.id)
        #     if jid in self.joystick_contextmenu_items:
        #         item = self.joystick_contextmenu_items[jid]
        #         item['item'].name = f"{item['joystick'].name} (ID: {jid})"
        #
        # js_control.callbacks.new_joystick.register(add_joystick_menu_item)
        # js_control.callbacks.joystick_disconnected.register(remove_joystick_menu_item)
        # js_control.callbacks.new_assignment.register(new_assignment)
        # js_control.callbacks.assigment_removed.register(assignment_removed)
        #
        # # Click callback on the joystick indicator
        # def joystick_indicator_click_callback(*args, **kwargs):
        #     # Check if our robot has a joystick assigned
        #     if js_control is not None:
        #         joystick = js_control.robotIsAssigned(self.robot)
        #         if joystick is not None:
        #             # If so, open the context menu
        #             joystick.rumble(strength=1, duration=1000)
        #
        # self.joystick_indicator.callbacks.click.register(joystick_indicator_click_callback)

        # Control Group
        control_group = Widget_Group(title='Control', rows=10, columns=10, show_title=True)
        page.addWidget(control_group, column=1, width=11, height=12)

        self.control_status_widget = StatusWidget(
            widget_id='control_status_widget',
            title='Status',
            elements={
                'mode': StatusWidgetElement(label='Control Mode',
                                            color=CONTROL_MODE_COLORS[self.robot.control.mode],
                                            status=self.robot.control.mode.name,
                                            ),
                'tic': StatusWidgetElement(label='Theta IntCtrl',
                                           color=[0.5, 0.5, 0.5] if not self.robot.core.data.control.tic_enabled else [
                                               0, 0.5, 0],
                                           status='disabled' if not self.robot.core.data.control.tic_enabled else 'enabled',
                                           ),
                'vic': StatusWidgetElement(label='Velocity IntCtrl',
                                           color=[0.5, 0.5, 0.5] if not self.robot.core.data.control.vic_enabled else [
                                               0, 0.5, 0],
                                           status='disabled' if not self.robot.core.data.control.vic_enabled else 'enabled',
                                           ),
                'static': StatusWidgetElement(label='Static',
                                              color=[0.5, 0.5, 0.5],
                                              status='false',
                                              ),

            }
        )
        control_group.addWidget(self.control_status_widget, row=1, column=1, width=10, height=4)

        tic_button = MultiStateButton(
            id='tic_button',
            title='TIC',
            widget_id='tic_button',
            states=[
                'OFF', 'ON'
            ],
            current_state=self.robot.core.data.control.tic_enabled,
            color=[
                [0.5, 0.5, 0.5],
                [0, 0.3, 0],
            ]
        )

        def tic_button_clicked(state: str, *args, **kwargs):
            match state:
                case 'ON':
                    self.robot.control.enableTIC(False)
                case 'OFF':
                    self.robot.control.enableTIC(True)

        def on_tic_mode_changed(enabled: bool, *args, **kwargs):
            if enabled:
                tic_button.state = 'ON'
            else:
                tic_button.state = 'OFF'

        tic_button.callbacks.click.register(tic_button_clicked)
        self.robot.control.events.tic_mode_changed.on(on_tic_mode_changed)

        control_group.addWidget(tic_button, column=1, row=8, width=2, height=2)

        self.mode_widget = BilboModeWidget(current_mode=self.robot.control.mode.name)
        control_group.addWidget(self.mode_widget, column=1, height=3, width=10)

        def update_mode_widget(mode: BILBO_Control_Mode, *args, **kwargs):
            self.mode_widget.current_mode = mode.name

        def mode_widget_click_callback(mode_id, *args, **kwargs):
            match mode_id:
                case 'OFF':
                    self.robot.control.setControlMode(BILBO_Control_Mode.OFF)
                case 'DIRECT':
                    self.robot.control.setControlMode(BILBO_Control_Mode.DIRECT)
                case 'POSITION':
                    self.robot.control.setControlMode(BILBO_Control_Mode.POSITION)
                case 'VELOCITY':
                    self.robot.control.setControlMode(BILBO_Control_Mode.VELOCITY)
                case 'BALANCING':
                    self.robot.control.setControlMode(BILBO_Control_Mode.BALANCING)

        self.mode_widget.callbacks.mode_clicked.register(mode_widget_click_callback)
        self.robot.control.events.mode_changed.on(update_mode_widget)

        self.robot.control.events.mode_changed.on(update_mode_widget)

        states_group = Widget_Group(title='States', rows=7, columns=10, show_title=True)
        page.addWidget(states_group, column=12, width=10, height=8)
        self.x_digital_number = DigitalNumberWidget(widget_id='x_digital_number',
                                                    title='X',
                                                    min_value=-9,
                                                    max_value=9,
                                                    increment=0.01,
                                                    )
        states_group.addWidget(self.x_digital_number, row=1, column=1, width=7, height=1)

        self.y_digital_number = DigitalNumberWidget(widget_id='y_digital_number',
                                                    title='Y',
                                                    min_value=-9,
                                                    max_value=9,
                                                    increment=0.01,
                                                    )
        states_group.addWidget(self.y_digital_number, row=2, column=1, width=7, height=1)

        self.v_digital_number = DigitalNumberWidget(widget_id='v_digital_number',
                                                    title='V',
                                                    min_value=-9,
                                                    max_value=9,
                                                    increment=0.01,
                                                    color_ranges=[
                                                        {'min': -0.05, 'max': 0.05, 'color': [0, 0.8, 0]}
                                                    ]
                                                    )
        states_group.addWidget(self.v_digital_number, row=3, column=1, width=7, height=1)
        self.theta_digital_number = DigitalNumberWidget(widget_id='theta_digital_number',
                                                        title='Theta (deg)',
                                                        min_value=-999,
                                                        max_value=999,
                                                        increment=0.1,
                                                        color_ranges=[
                                                            {'min': -0.15, 'max': 0.15, 'color': [0, 0.8, 0]}
                                                        ]
                                                        )

        states_group.addWidget(self.theta_digital_number, row=4, column=1, width=7, height=1)

        theta_button = Button(widget_id='theta_button', text='→ rad', color=[0.4, 0.4, 0.4])
        self.overview_page_data['theta_digital_number_format'] = 'grad'

        def theta_button_click(*args, **kwargs):
            if self.overview_page_data['theta_digital_number_format'] == 'rad':
                self.overview_page_data['theta_digital_number_format'] = 'grad'
                theta_button.updateConfig(text='→ rad')
                self.theta_digital_number.updateConfig(title='Theta (deg)')
                self.theta_digital_number.format = 'grad'
            else:
                self.overview_page_data['theta_digital_number_format'] = 'rad'
                theta_button.updateConfig(text='→ deg')
                self.theta_digital_number.updateConfig(title='Theta (rad)')
                self.theta_digital_number.format = 'rad'

        theta_button.callbacks.click.register(theta_button_click)

        states_group.addWidget(theta_button, row=4, column=8, width=3, height=1)
        self.theta_dot_digital_number = DigitalNumberWidget(widget_id='theta_dot_digital_number',
                                                            title='Theta Dot (deg)',
                                                            min_value=-999,
                                                            max_value=999,
                                                            increment=0.1,
                                                            )
        states_group.addWidget(self.theta_dot_digital_number, row=5, column=1, width=7, height=1)
        theta_dot_button = Button(widget_id='theta_dot_button', text='→ rad', color=[0.4, 0.4, 0.4])

        self.overview_page_data['theta_dot_digital_number_format'] = 'grad'

        def theta_dot_button_click(*args, **kwargs):
            if self.overview_page_data['theta_dot_digital_number_format'] == 'rad':
                self.overview_page_data['theta_dot_digital_number_format'] = 'grad'
                theta_dot_button.updateConfig(text='→ rad')
                self.theta_dot_digital_number.updateConfig(title='Theta Dot (deg)')
                self.theta_dot_digital_number.format = 'grad'
            else:
                self.overview_page_data['theta_dot_digital_number_format'] = 'rad'
                theta_dot_button.updateConfig(text='→ deg')
                self.theta_dot_digital_number.updateConfig(title='Theta Dot (rad)')
                self.theta_dot_digital_number.format = 'rad'

        theta_dot_button.callbacks.click.register(theta_dot_button_click)

        states_group.addWidget(theta_dot_button, row=5, column=8, width=3, height=1)
        self.psi_digital_number = DigitalNumberWidget(widget_id='psi_digital_number',
                                                      title='Psi (deg)',
                                                      min_value=-999,
                                                      max_value=999,
                                                      increment=0.1,
                                                      )
        states_group.addWidget(self.psi_digital_number, row=6, column=1, width=7, height=1)
        psi_button = Button(widget_id='psi_button', text='→ rad', color=[0.4, 0.4, 0.4])

        self.overview_page_data['psi_digital_number_format'] = 'grad'

        def psi_button_click(*args, **kwargs):
            if self.overview_page_data['psi_digital_number_format'] == 'rad':
                self.overview_page_data['psi_digital_number_format'] = 'grad'
                psi_button.updateConfig(text='→ rad')
                self.psi_digital_number.updateConfig(title='Psi (deg)')
                self.psi_digital_number.format = 'grad'
            else:
                self.overview_page_data['psi_digital_number_format'] = 'rad'
                psi_button.updateConfig(text='→ deg')
                self.psi_digital_number.updateConfig(title='Psi (rad)')
                self.psi_digital_number.format = 'rad'

        psi_button.callbacks.click.register(psi_button_click)

        states_group.addWidget(psi_button, row=6, column=8, width=3, height=1)
        self.psi_dot_digital_number = DigitalNumberWidget(widget_id='psi_dot_digital_number',
                                                          title='Psi Dot (deg)',
                                                          min_value=-999,
                                                          max_value=999,
                                                          increment=0.1,
                                                          )
        states_group.addWidget(self.psi_dot_digital_number, row=7, column=1, width=7, height=1)
        psi_dot_button = Button(widget_id='psi_dot_button', text='→ rad', color=[0.4, 0.4, 0.4])

        self.overview_page_data['psi_dot_digital_number_format'] = 'grad'

        def psi_dot_button_click(*args, **kwargs):
            if self.overview_page_data['psi_dot_digital_number_format'] == 'rad':
                self.overview_page_data['psi_dot_digital_number_format'] = 'grad'
                psi_dot_button.updateConfig(text='→ rad')
                self.psi_dot_digital_number.updateConfig(title='Psi Dot (deg)')
                self.psi_dot_digital_number.format = 'grad'
            else:
                self.overview_page_data['psi_dot_digital_number_format'] = 'rad'
                psi_dot_button.updateConfig(text='→ deg')
                self.psi_dot_digital_number.updateConfig(title='Psi Dot (rad)')
                self.psi_dot_digital_number.format = 'rad'

        psi_dot_button.callbacks.click.register(psi_dot_button_click)

        states_group.addWidget(psi_dot_button, row=7, column=8, width=3, height=1)

        # === ESTIMATION GROUP ===
        estimation_group = Widget_Group(title='Estimation', rows=7, columns=10, show_title=True)
        page.addWidget(estimation_group, column=22, row=1, width=9, height=8)

        # Status widget showing dead-reckoning vs tracked
        self.estimation_status_widget = StatusWidget(
            widget_id='estimation_status_widget',
            title='Status',
            elements={
                'tracking': StatusWidgetElement(
                    label='Source',
                    color=[0.6, 0.2, 0.2],  # Red for dead-reckoning initially
                    status='Dead-Reckoning',
                ),
            }
        )
        estimation_group.addWidget(self.estimation_status_widget, row=1, column=1, width=10, height=2)

        # Reset estimation button
        self.reset_estimation_button = Button(
            widget_id='reset_estimation_button',
            text='Reset Estimation',
            color=[0.5, 0.3, 0.2],
        )
        estimation_group.addWidget(self.reset_estimation_button, row=3, column=1, width=10, height=1)

        def on_reset_estimation_clicked(*args, **kwargs):
            self.logger.info("Resetting estimation")
            self.robot.estimation.reset()

        self.reset_estimation_button.callbacks.click.register(on_reset_estimation_clicked)

        # Gyroscope readings (smaller digital numbers)
        gyro_label = TextWidget(widget_id='gyro_label', text='Gyro (deg/s)', fontSize=10,
                                textColor=[0.7, 0.7, 0.7, 1.0])
        estimation_group.addWidget(gyro_label, row=4, column=1, width=10, height=1)

        self.gyro_x_number = DigitalNumberWidget(
            widget_id='gyro_x_number',
            title='X',
            min_value=-999,
            max_value=999,
            increment=0.1,
        )
        estimation_group.addWidget(self.gyro_x_number, row=5, column=1, width=3, height=1)

        self.gyro_y_number = DigitalNumberWidget(
            widget_id='gyro_y_number',
            title='Y',
            min_value=-999,
            max_value=999,
            increment=0.1,
        )
        estimation_group.addWidget(self.gyro_y_number, row=5, column=4, width=3, height=1)

        self.gyro_z_number = DigitalNumberWidget(
            widget_id='gyro_z_number',
            title='Z',
            min_value=-999,
            max_value=999,
            increment=0.1,
        )
        estimation_group.addWidget(self.gyro_z_number, row=5, column=7, width=3, height=1)

        # Accelerometer readings (smaller digital numbers)
        acc_label = TextWidget(widget_id='acc_label', text='Acc (m/s²)', fontSize=10, textColor=[0.7, 0.7, 0.7, 1.0])
        estimation_group.addWidget(acc_label, row=6, column=1, width=10, height=1)

        self.acc_x_number = DigitalNumberWidget(
            widget_id='acc_x_number',
            title='X',
            min_value=-99,
            max_value=99,
            increment=0.01,
        )
        estimation_group.addWidget(self.acc_x_number, row=7, column=1, width=3, height=1)

        self.acc_y_number = DigitalNumberWidget(
            widget_id='acc_y_number',
            title='Y',
            min_value=-99,
            max_value=99,
            increment=0.01,
        )
        estimation_group.addWidget(self.acc_y_number, row=7, column=4, width=3, height=1)

        self.acc_z_number = DigitalNumberWidget(
            widget_id='acc_z_number',
            title='Z',
            min_value=-99,
            max_value=99,
            increment=0.01,
        )
        estimation_group.addWidget(self.acc_z_number, row=7, column=7, width=3, height=1)

        # Make the plots

        palette = get_palette('pastel', 7)

        v_plot = RT_Plot_Widget(
            widget_id='v_plot',
            plot_config={
                'title': 'V',
                'show_title': True,
                "legend_label_type": "point",
            }
        )
        y_axis_v = v_plot.plot.add_y_axis(
            'v',
            {
                "label": f"v [m/s]",
                "min": -2,
                "max": 2,
                "color": palette[0],
                "grid_color": [0.5, 0.5, 0.5, 0.4],
                "precision": 2,
                "highlight_zero": True,
                "side": "left",
            },
        )
        self.timeseries_v = TimeSeries(
            id='v',
            y_axis=y_axis_v,  # can pass the object or its id
            name='v',
            unit='m/s',
            color=palette[0],
            fill=False,
            tension=0.0,
            precision=1,
            width=2,
        )
        self.timeseries_v.set_value(0.0)
        v_plot.plot.add_timeseries(self.timeseries_v)
        page.addWidget(v_plot, column=31, row=7, width=10, height=6)

        theta_plot = RT_Plot_Widget(
            widget_id='theta_plot',
            plot_config={
                'title': 'Theta',
                'show_title': True,
                "legend_label_type": "point",
            }
        )
        y_axis_theta = theta_plot.plot.add_y_axis(
            'theta',
            {
                "label": f"Theta [deg]",
                "min": -100,
                "max": 100,
                "color": palette[1],
                "grid_color": [0.5, 0.5, 0.5, 0.4],
                "precision": 1,
                "highlight_zero": True,
            }
        )
        self.timeseries_theta = TimeSeries(
            id='theta',
            y_axis=y_axis_theta,  # can pass the object or its id
            name='theta',
            unit='deg',
            color=palette[1],
            fill=False,
            tension=0.0,
            precision=1,
            width=2,
        )
        theta_plot.plot.add_timeseries(self.timeseries_theta)
        page.addWidget(theta_plot, column=41, row=1, width=10, height=6)

        theta_dot_plot = RT_Plot_Widget(
            widget_id='theta_dot_plot',
            plot_config={
                'title': 'Theta Dot',
                'show_title': True,
                "legend_label_type": "point",
            }
        )
        y_axis_theta_dot = theta_dot_plot.plot.add_y_axis(
            'theta_dot',
            {
                "label": f"Theta Dot [deg/s]",
                "min": -300,
                "max": 300,
                "color": palette[2],
                "grid_color": [0.5, 0.5, 0.5, 0.4],
                "precision": 1,
                "highlight_zero": True,
            }
        )
        self.theta_dot_timeseries = TimeSeries(
            id='theta_dot',
            y_axis=y_axis_theta_dot,  # can pass the object or its id
            name='theta_dot',
            unit='deg',
            color=palette[2],
            fill=False,
            tension=0.0,
            precision=1,
            width=2,
        )
        theta_dot_plot.plot.add_timeseries(self.theta_dot_timeseries)
        page.addWidget(theta_dot_plot, column=41, row=7, width=10, height=6)

        psi_plot = RT_Plot_Widget(
            widget_id='psi_plot',
            plot_config={
                'title': 'Psi',
                'show_title': True,
                "legend_label_type": "point",
            }
        )
        y_axis_psi = psi_plot.plot.add_y_axis(
            'psi',
            {
                "label": f"Psi [deg]",
                "min": -180,
                "max": 180,
                "color": palette[3],
                "grid_color": [0.5, 0.5, 0.5, 0.4],
                "precision": 1,
                "highlight_zero": True,
            }
        )
        self.psi_plot_timeseries = TimeSeries(
            id='psi',
            y_axis=y_axis_psi,  # can pass the object or its id
            name='psi',
            unit='deg',
            color=palette[3],
            fill=False,
            tension=0.0,
            precision=1,
            width=2,
        )
        psi_plot.plot.add_timeseries(self.psi_plot_timeseries)
        page.addWidget(psi_plot, column=31, row=13, width=10, height=6)

        psi_dot_plot = RT_Plot_Widget(
            widget_id='psi_dot_plot',
            plot_config={
                'title': 'Psi Dot',
                'show_title': True,
                "legend_label_type": "point",
            }
        )
        y_axis_psi_dot = psi_dot_plot.plot.add_y_axis(
            'psi_dot',
            {
                "label": f"Psi Dot [deg/s]",
                "min": -200,
                "max": 200,
                "color": palette[4],
                "precision": 1,
                "highlight_zero": True,
            }
        )
        self.psi_dot_timeseries = TimeSeries(
            id='psi_dot',
            y_axis=y_axis_psi_dot,  # can pass the object or its id
            name='psi_dot',
            unit='deg/s',
            color=palette[4],
            fill=False,
            tension=0.0,
            precision=1,
            width=2,
        )
        psi_dot_plot.plot.add_timeseries(self.psi_dot_timeseries)
        page.addWidget(psi_dot_plot, column=41, row=13, width=10, height=6)

        position_plot = RT_Plot_Widget(
            widget_id='position_plot',
            plot_config={
                'title': 'Position',
                'show_title': True,
                "legend_label_type": "point",
            }
        )
        y_axis_position = position_plot.plot.add_y_axis(
            'position',
            {
                "label": f"Position [m]",
                "min": -4,
                "max": 4,
                "color": [0.5, 0.5, 0.5, 0.7],
                "grid_color": [0.5, 0.5, 0.5, 0.4],
                "precision": 1,
                "highlight_zero": True,
            }
        )
        self.x_timeseries = TimeSeries(
            id='x',
            y_axis=y_axis_position,  # can pass the object or its id
            name='x',
            unit='m',
            color=palette[5],
            fill=False,
            tension=0.0,
            precision=1,
            width=2,
        )
        self.x_timeseries.set_value(0.0)
        position_plot.plot.add_timeseries(self.x_timeseries)

        self.y_timeseries = TimeSeries(
            id='y',
            y_axis=y_axis_position,  # can pass the object or its id
            name='y',
            unit='m',
            color=palette[6],
            fill=False,
            tension=0.0,
            precision=1,
            width=2,
        )
        self.y_timeseries.set_value(0.0)
        position_plot.plot.add_timeseries(self.y_timeseries)
        page.addWidget(position_plot, column=31, row=1, width=10, height=6)

        self.plots.append(v_plot)
        self.plots.append(theta_plot)
        self.plots.append(theta_dot_plot)
        self.plots.append(psi_plot)
        self.plots.append(psi_dot_plot)
        self.plots.append(position_plot)

        testbed_size = self.manager.settings.testbed.size
        self.map_widget = MapWidget(widget_id='map_widget',
                                    title='Testbed',
                                    limits={"x": [self.manager.settings.testbed.size['x'][0],
                                                  self.manager.settings.testbed.size['x'][1]],
                                            "y": [self.manager.settings.testbed.size['y'][0],
                                                  self.manager.settings.testbed.size['y'][1]]},
                                    initial_display_center=[(self.manager.settings.testbed.size['x'][0] +
                                                             self.manager.settings.testbed.size['x'][1]) / 2,
                                                            (self.manager.settings.testbed.size['y'][0] +
                                                             self.manager.settings.testbed.size['y'][1]) / 2],
                                    tiles=True,
                                    tile_size=0.5,
                                    show_grid=False,
                                    )

        # Single map agent — color changes based on tracking source:
        #   Green = tracked (OptiTrack), Red = dead-reckoning
        self.robot_map_agent = Agent(
            id=f"robot_map_agent", x=0, y=0, psi=0,
            size=0.1, arrow_length=0.25, arrow_width=0.05,
            color=[0.6, 0.2, 0.2],  # Red (dead-reckoning) initially
            show_name=False
        )
        self._first_stream_tick: int | None = None
        self._agent_is_tracked: bool = False  # current color state
        self.map_widget.map.addObject(self.robot_map_agent)

        def map_double_click(data, *args, **kwargs):
            x = data['x']
            y = data['y']
            if testbed_size['x'][0] < x < testbed_size['x'][1] and testbed_size['y'][0] < y < testbed_size['y'][1]:
                if self.nav_mode_button.state == 'Path':
                    self.robot.position_control.plan_and_follow(target=(x, y))
                else:
                    self.robot.position_control.move_to(x, y)
            else:
                self.logger.warning(f"Position out of bounds: {x}, {y}")

        self.map_widget.map.events.double_click.on(map_double_click)

        # === POSITION CONTROL VISUALIZATION ===
        STOP_POINT_COLOR = [1.0, 0.4, 0.2, 1.0]    # Orange for stop points
        STOP_DIM_ALPHA = 0.3                         # Alpha for completed stop points
        PATH_LINE_COLOR = [0.4, 0.7, 1.0, 0.6]      # Light blue for path lines
        MOVE_TO_POINT_COLOR = [0.9, 0.3, 0.9, 1.0]  # Magenta for move_to_point target
        TURN_TO_HEADING_COLOR = [0.2, 0.9, 0.5, 0.8]  # Green for turn_to_heading indicator

        # Track path stop point objects for completion dimming
        self._path_stop_objects: list[Point] = []
        self._path_line_objects: list[Line] = []
        self._planned_path_objects: list[MapObject] = []
        self._planning_preview_objects: list[MapObject] = []

        def _clear_position_objects():
            """Clear all position control visualization objects"""
            for obj in self._additional_map_objects:
                try:
                    if obj.id in self.map_widget.map.objects:
                        self.map_widget.map.removeObject(obj)
                except Exception:
                    pass
            self._additional_map_objects = []
            self._path_stop_objects = []
            self._path_line_objects = []

        def _clear_planned_path():
            """Clear planned path preview objects"""
            for obj in self._planned_path_objects:
                try:
                    if obj.id in self.map_widget.map.objects:
                        self.map_widget.map.removeObject(obj)
                except Exception:
                    pass
            self._planned_path_objects = []

        # --- Planning preview (shown immediately on path_planning_started) ---
        PLANNING_START_COLOR = [0.3, 0.9, 0.3, 0.9]         # Green for start point
        PLANNING_TARGET_COLOR = [1.0, 0.3, 0.3, 0.9]        # Red for target point
        PLANNING_WAYPOINT_COLOR = [0.5, 0.6, 1.0, 0.8]      # Blue for waypoints
        PLANNING_PREVIEW_SIZE = 0.04
        PLANNING_PREVIEW_BORDER = [1.0, 1.0, 1.0, 0.8]

        def _clear_planning_preview():
            """Clear planning preview markers (start/target/waypoints shown before plan is ready)."""
            for obj in self._planning_preview_objects:
                try:
                    if obj.id in self.map_widget.map.objects:
                        self.map_widget.map.removeObject(obj)
                except Exception:
                    pass
            self._planning_preview_objects = []

        def _on_path_planning_started(data, *args, **kwargs):
            """Draw start, target, and waypoints immediately when planning begins."""
            if data is None:
                return
            _clear_planning_preview()

            start = data.get('start')
            target = data.get('target')
            waypoints = data.get('waypoints', [])

            if start:
                pt = Point(
                    id=f"planning_start_{generate_uuid()[:8]}",
                    x=start['x'], y=start['y'],
                    size=PLANNING_PREVIEW_SIZE,
                    color=PLANNING_START_COLOR,
                    border_color=PLANNING_PREVIEW_BORDER,
                    border_width=2,
                    shape='circle',
                    show_name=False,
                )
                self.map_widget.map.addObject(pt)
                self._planning_preview_objects.append(pt)

            if target:
                pt = Point(
                    id=f"planning_target_{generate_uuid()[:8]}",
                    x=target['x'], y=target['y'],
                    size=PLANNING_PREVIEW_SIZE * 1.2,
                    color=PLANNING_TARGET_COLOR,
                    border_color=PLANNING_PREVIEW_BORDER,
                    border_width=2,
                    shape='star',
                    show_name=False,
                )
                self.map_widget.map.addObject(pt)
                self._planning_preview_objects.append(pt)

            for i, wp in enumerate(waypoints):
                pt = Point(
                    id=f"planning_wp_{i}_{generate_uuid()[:8]}",
                    x=wp['x'], y=wp['y'],
                    size=PLANNING_PREVIEW_SIZE * 0.8,
                    color=PLANNING_WAYPOINT_COLOR,
                    border_color=PLANNING_PREVIEW_BORDER,
                    border_width=1,
                    shape='diamond',
                    show_name=False,
                )
                self.map_widget.map.addObject(pt)
                self._planning_preview_objects.append(pt)

        self.robot.position_control.events.path_planning_started.on(_on_path_planning_started)

        def _on_position_mode_changed(*args, **kwargs):
            _clear_planning_preview()
            if self._additional_map_objects:
                _clear_position_objects()

        self.robot.position_control.events.mode_changed.on(_on_position_mode_changed)

        def _on_path_loaded(path_data: PathData, *args, **kwargs):
            """Visualize loaded dense path — path info only (no individual points)"""
            if not path_data or path_data.path_point_count == 0:
                return

            _clear_position_objects()

            # For dense paths we don't visualize individual points (too many).
            # We show stop indices as orange markers if available.
            # The actual path polyline would require the full point data
            # which is only on the robot/firmware side.

        self.robot.position_control.events.path_loaded.on(_on_path_loaded)

        def _on_path_started(path_data: PathData, *args, **kwargs):
            """Ensure visualization exists when path starts"""
            if not path_data or path_data.path_point_count == 0:
                return
            if not self._path_stop_objects and not self._path_line_objects:
                _on_path_loaded(path_data)

        self.robot.position_control.events.path_started.on(_on_path_started)

        def _on_path_finished(*args, **kwargs):
            """Clear path visualization when finished"""
            _clear_position_objects()
            _clear_planning_preview()

        self.robot.position_control.events.path_finished.on(_on_path_finished)
        self.robot.position_control.events.path_aborted.on(_on_path_finished)
        self.robot.position_control.events.path_timeout.on(_on_path_finished)

        def _on_stop_completed(data: dict, *args, **kwargs):
            """Dim completed stop point"""
            if data is None:
                return
            idx = data.get('index', 0)

            # Dim the completed stop point
            if idx < len(self._path_stop_objects):
                obj = self._path_stop_objects[idx]
                current_color = obj.config.get('color', [0.5, 0.5, 0.5, 1.0])
                dimmed_color = current_color[:3] + [STOP_DIM_ALPHA]
                obj.updateConfig(color=dimmed_color)

        self.robot.position_control.events.stop_completed.on(_on_stop_completed)

        def _on_move_to_point_started(command: MoveToPointCommand, *args, **kwargs):
            """Show move_to_point target"""
            if command is None:
                return

            point = Point(
                id=f"move_to_target_{generate_uuid()[:8]}",
                x=command.x,
                y=command.y,
                size=0.07,
                color=MOVE_TO_POINT_COLOR,
                border_color=[1, 1, 1, 0.9],
                border_width=2,
                shape='circle',
                show_name=False,
            )
            self.map_widget.map.addObject(point)
            self._additional_map_objects.append(point)

        self.robot.position_control.events.move_to_point_started.on(_on_move_to_point_started)

        def _on_move_to_point_completed(*args, **kwargs):
            """Dim move_to_point target when completed"""
            # Find and dim the target point (last added point with move_to color)
            for obj in reversed(self._additional_map_objects):
                if isinstance(obj, Point) and obj.id.startswith('move_to_target_'):
                    current_color = obj.config.get('color', MOVE_TO_POINT_COLOR)
                    dimmed_color = current_color[:3] + [STOP_DIM_ALPHA]
                    obj.updateConfig(color=dimmed_color)
                    break

        self.robot.position_control.events.move_to_point_completed.on(_on_move_to_point_completed)
        self.robot.position_control.events.move_to_point_timeout.on(_on_move_to_point_completed)

        def _on_turn_to_heading_started(command: TurnToHeadingCommand, *args, **kwargs):
            """Show turn_to_heading indicator as a line from robot"""
            if command is None:
                return

            # Get current robot position
            robot_x = self.robot_map_agent.data.get('x', 0)
            robot_y = self.robot_map_agent.data.get('y', 0)

            # Calculate endpoint of heading indicator line
            line_length = 0.3
            end_x = robot_x + line_length * math.cos(command.heading)
            end_y = robot_y + line_length * math.sin(command.heading)

            # Create start point (at robot position, small)
            start_point = Point(
                id=f"heading_start_{generate_uuid()[:8]}",
                x=robot_x,
                y=robot_y,
                size=0.02,
                color=TURN_TO_HEADING_COLOR,
                show_name=False,
            )
            self.map_widget.map.addObject(start_point)
            self._additional_map_objects.append(start_point)

            # Create end point (at target heading)
            end_point = Point(
                id=f"heading_end_{generate_uuid()[:8]}",
                x=end_x,
                y=end_y,
                size=0.04,
                color=TURN_TO_HEADING_COLOR,
                border_color=[1, 1, 1, 0.8],
                border_width=1,
                shape='triangle',
                show_name=False,
            )
            self.map_widget.map.addObject(end_point)
            self._additional_map_objects.append(end_point)

            # Create line between them
            line = Line(
                id=f"heading_line_{generate_uuid()[:8]}",
                start=start_point,
                end=end_point,
                color=TURN_TO_HEADING_COLOR,
                width=2,
                style='solid',
                show_name=False,
            )
            self.map_widget.map.addObject(line)
            self._additional_map_objects.append(line)

        self.robot.position_control.events.turn_to_heading_started.on(_on_turn_to_heading_started)

        def _on_turn_to_heading_completed(*args, **kwargs):
            """Dim turn_to_heading indicator when completed"""
            # Find and dim the heading indicator objects
            for obj in self._additional_map_objects:
                if isinstance(obj, (Point, Line)) and ('heading_' in obj.id):
                    current_color = obj.config.get('color', TURN_TO_HEADING_COLOR)
                    dimmed_color = current_color[:3] + [STOP_DIM_ALPHA]
                    obj.updateConfig(color=dimmed_color)

        self.robot.position_control.events.turn_to_heading_completed.on(_on_turn_to_heading_completed)
        self.robot.position_control.events.turn_to_heading_timeout.on(_on_turn_to_heading_completed)

        # --- Obstacle visualization (from testbed) ---
        OBSTACLE_FILL_COLOR = [0.9, 0.2, 0.2, 0.3]          # Transparent red fill
        OBSTACLE_BORDER_COLOR = [1.0, 1.0, 1.0, 0.8]        # White border
        OBSTACLE_BORDER_WIDTH = 2

        def _add_obstacle_to_map(obstacle, *args, **kwargs):
            """Add a testbed obstacle to the 2D map."""
            if not isinstance(obstacle, BoxObstacle):
                return
            obs_id = obstacle.id
            if obs_id in self._obstacle_map_objects:
                return
            state = obstacle.state
            map_obj = Rectangle(
                id=f"obstacle_{obs_id}",
                x=state.x, y=state.y, psi=state.psi,
                width=obstacle.config.width, height=obstacle.config.height,
                color=OBSTACLE_FILL_COLOR,
                border_color=OBSTACLE_BORDER_COLOR,
                border_width=OBSTACLE_BORDER_WIDTH,
                show_name=False,
                layer=0,
            )
            self.map_widget.map.addObject(map_obj)
            self._obstacle_map_objects[obs_id] = map_obj

        def _remove_obstacle_from_map(obstacle, *args, **kwargs):
            """Remove a testbed obstacle from the 2D map."""
            if isinstance(obstacle, BoxObstacle):
                obs_id = obstacle.id
            elif isinstance(obstacle, str):
                obs_id = obstacle
            else:
                return
            if obs_id in self._obstacle_map_objects:
                obj = self._obstacle_map_objects.pop(obs_id)
                try:
                    self.map_widget.map.removeObject(obj)
                except Exception:
                    pass

        # Add existing obstacles
        for obs in self.manager.testbed.obstacles.values():
            _add_obstacle_to_map(obs)

        # Subscribe to testbed obstacle events
        self.manager.testbed.events.obstacle_added.on(_add_obstacle_to_map)
        self.manager.testbed.events.obstacle_removed.on(_remove_obstacle_from_map)

        # --- Planned path visualization ---
        PLANNED_PATH_COLOR = [0.4, 0.8, 1.0, 0.5]          # Light blue, semi-transparent
        PLANNED_PATH_POINT_SIZE = 0.015                      # Small dots along path
        PLANNED_PATH_LINE_WIDTH = 2
        PLANNED_PATH_TARGET_COLOR = [0.2, 1.0, 0.4, 0.9]   # Green target point
        PLANNED_PATH_TARGET_SIZE = 0.04
        PLANNED_PATH_SUBSAMPLE = 5                           # Show every Nth point to avoid clutter
        WAYPOINT_PASS_COLOR = [1.0, 0.8, 0.2, 0.9]         # Yellow for PASS waypoints
        WAYPOINT_STOP_COLOR = [1.0, 0.3, 0.3, 0.9]         # Red for STOP waypoints
        WAYPOINT_SIZE = 0.035                                # Waypoint marker size
        WAYPOINT_BORDER_COLOR = [1.0, 1.0, 1.0, 0.9]       # White border

        def _draw_planned_path(path_data: PathData):
            """Draw a planned/loaded path as a polyline with target marker."""
            _clear_planned_path()

            points = path_data.path_points
            if not points or len(points) < 2:
                return

            # Subsample for visualization (dense paths may have 500+ points)
            vis_indices = list(range(0, len(points), PLANNED_PATH_SUBSAMPLE))
            if vis_indices[-1] != len(points) - 1:
                vis_indices.append(len(points) - 1)

            # Create point objects along the path
            prev_point_obj = None
            for i, idx in enumerate(vis_indices):
                x, y = points[idx]
                is_last = (idx == len(points) - 1)

                pt = Point(
                    id=f"planned_path_pt_{generate_uuid()[:8]}",
                    x=x, y=y,
                    size=PLANNED_PATH_TARGET_SIZE if is_last else PLANNED_PATH_POINT_SIZE,
                    color=PLANNED_PATH_TARGET_COLOR if is_last else PLANNED_PATH_COLOR,
                    border_color=[1, 1, 1, 0.8] if is_last else [0, 0, 0, 0],
                    border_width=2 if is_last else 0,
                    shape='circle',
                    show_name=False,
                )
                self.map_widget.map.addObject(pt)
                self._planned_path_objects.append(pt)

                # Connect consecutive points with lines
                if prev_point_obj is not None:
                    ln = Line(
                        id=f"planned_path_ln_{generate_uuid()[:8]}",
                        start=prev_point_obj,
                        end=pt,
                        color=PLANNED_PATH_COLOR,
                        width=PLANNED_PATH_LINE_WIDTH,
                        style='solid',
                        show_name=False,
                    )
                    self.map_widget.map.addObject(ln)
                    self._planned_path_objects.append(ln)

                prev_point_obj = pt

            # Draw waypoint markers (on top of path)
            if path_data.waypoints:
                for i, wp in enumerate(path_data.waypoints):
                    wx = wp.get('x', 0)
                    wy = wp.get('y', 0)
                    wp_type = wp.get('type', 'PASS').upper()
                    is_stop = wp_type == 'STOP'
                    color = WAYPOINT_STOP_COLOR if is_stop else WAYPOINT_PASS_COLOR

                    wp_pt = Point(
                        id=f"planned_path_wp_{generate_uuid()[:8]}",
                        x=wx, y=wy,
                        size=WAYPOINT_SIZE,
                        color=color,
                        border_color=WAYPOINT_BORDER_COLOR,
                        border_width=2,
                        shape='diamond',
                        show_name=False,
                    )
                    self.map_widget.map.addObject(wp_pt)
                    self._planned_path_objects.append(wp_pt)

        def _on_path_planned(path_data: PathData, *args, **kwargs):
            """Visualize a planned path preview."""
            _clear_planning_preview()
            if not path_data or path_data.path_point_count == 0:
                return
            _draw_planned_path(path_data)

        self.robot.position_control.events.path_planned.on(_on_path_planned)

        # Also draw path when loaded (has compressed points now)
        def _on_path_loaded_viz(path_data: PathData, *args, **kwargs):
            _clear_planning_preview()
            if not path_data or not path_data.path_points:
                return
            _draw_planned_path(path_data)

        self.robot.position_control.events.path_loaded.on(_on_path_loaded_viz)

        # Clear planned path when path finishes/aborts/cleared or a new path starts
        self.robot.position_control.events.path_finished.on(lambda *a, **kw: _clear_planned_path())
        self.robot.position_control.events.path_aborted.on(lambda *a, **kw: _clear_planned_path())
        self.robot.position_control.events.path_timeout.on(lambda *a, **kw: _clear_planned_path())
        self.robot.position_control.events.path_cleared.on(lambda *a, **kw: _clear_planned_path())

        navigation_group = Widget_Group(widget_id='navigation_group',
                                        title='Navigation',
                                        columns=9,
                                        rows=9,
                                        show_title=True,
                                        )
        page.addWidget(navigation_group, column=22, row=9, width=9, height=10)

        self.nav_mode_button = MultiStateButton(
            id='nav_mode_button',
            states=['MoveTo', 'Path'],
            current_state='Path',
            color=[
                [0.6, 0.3, 0.6],  # Purple for MoveTo
                [0.3, 0.5, 0.7],  # Blue for Path
            ],
            title='Click Mode',
        )
        navigation_group.addWidget(self.nav_mode_button, row=1, column=1, width=4, height=2)

        def nav_mode_clicked(state: str, *args, **kwargs):
            match state:
                case 'MoveTo':
                    self.nav_mode_button.state = 'Path'
                case 'Path':
                    self.nav_mode_button.state = 'MoveTo'

        self.nav_mode_button.callbacks.click.register(nav_mode_clicked)

        psi_zero_button = Button(widget_id='psi_zero_button', text='Ψ=0', color=[0.4, 0.4, 0.4])
        psi_zero_button.callbacks.click.register(lambda *args, **kwargs: self.robot.position_control.turn_to(0))
        navigation_group.addWidget(psi_zero_button, row=1, column=5, width=2, height=2)

        page.addWidget(self.map_widget, row=9, width=10, height=10)

    # ------------------------------------------------------------------------------------------------------------------
    def build_control_page(self, page):
        palette = get_palette('pastel', 4)
        input_plot = RT_Plot_Widget(
            widget_id='input_plot',
            plot_config={
                'title': 'Input',
                'show_title': True,
                "legend_label_type": "point",
            }
        )
        input_axis = input_plot.plot.add_y_axis(
            'input',
            {
                "label": f"Input [Nm]",
                "min": -0.5,
                "max": 0.5,
                "color": [0.5, 0.5, 0.5, 0.7],
                "grid_color": [0.5, 0.5, 0.5, 0.4],
                "precision": 1,
                "highlight_zero": True,
            }
        )
        self.input_left_timeseries = TimeSeries(
            id='left',
            y_axis=input_axis,  # can pass the object or its id
            name='left',
            unit='Nm',
            color=palette[0],
            fill=False,
            tension=0.0,
            precision=2,
            width=2,
        )
        self.input_right_timeseries = TimeSeries(
            id='right',
            y_axis=input_axis,  # can pass the object or its id
            name='right',
            unit='Nm',
            color=palette[1],
            fill=False,
            tension=0.0,
            precision=2,
            width=2,
        )
        input_plot.plot.add_timeseries(self.input_left_timeseries)
        input_plot.plot.add_timeseries(self.input_right_timeseries)
        page.addWidget(input_plot, column=1, row=1, width=16, height=14)

        # === VELOCITY PID CONTROL DIALS ===
        # Forward Velocity PID Group
        v_pid_group = Widget_Group(
            group_id='v_pid_group',
            title='Velocity PID (Forward)',
            rows=8,
            columns=12,
            show_title=True
        )
        page.addWidget(v_pid_group, column=17, row=1, width=12, height=9)

        # Kp dial for forward velocity (typical range: -0.1 to 0, default: -0.005)
        self.v_kp_dial = RotaryDialWidget(
            widget_id='v_kp_dial',
            min_value=-0.1,
            max_value=0.0,
            increment=0.001,
            value=-0.005,
            title='Kp',
            continuousUpdates=False,
            dialColor=[0.2, 0.5, 0.8, 1.0],
        )
        v_pid_group.addWidget(self.v_kp_dial, row=1, column=1, width=4, height=4)

        def on_v_kp_changed(value, *args, **kwargs):
            self.robot.control.set_forward_pid(P=value)

        self.v_kp_dial.callbacks.value_changed.register(on_v_kp_changed)

        # Ki dial for forward velocity (typical range: -1 to 0, default: -0.05)
        self.v_ki_dial = RotaryDialWidget(
            widget_id='v_ki_dial',
            min_value=-1.0,
            max_value=0.0,
            increment=0.01,
            value=-0.05,
            title='Ki',
            continuousUpdates=False,
            dialColor=[0.5, 0.2, 0.8, 1.0],
        )
        v_pid_group.addWidget(self.v_ki_dial, row=1, column=5, width=4, height=4)

        def on_v_ki_changed(value, *args, **kwargs):
            self.robot.control.set_forward_pid(I=value)

        self.v_ki_dial.callbacks.value_changed.register(on_v_ki_changed)

        # Kd dial for forward velocity (negative only: -0.01 to 0, default: 0)
        self.v_kd_dial = RotaryDialWidget(
            widget_id='v_kd_dial',
            min_value=-0.01,
            max_value=0.0,
            increment=0.0001,
            value=0.0,
            title='Kd',
            continuousUpdates=False,
            dialColor=[0.8, 0.5, 0.2, 1.0],
        )
        v_pid_group.addWidget(self.v_kd_dial, row=1, column=9, width=4, height=4)

        def on_v_kd_changed(value, *args, **kwargs):
            self.robot.control.set_forward_pid(D=value)

        self.v_kd_dial.callbacks.value_changed.register(on_v_kd_changed)

        # Enable I-Limit checkbox
        self.v_enable_i_limit_checkbox = CheckboxWidget(
            widget_id='v_enable_i_limit',
            value=False,
            title='I-Limit:',
            title_position='left',
        )
        v_pid_group.addWidget(self.v_enable_i_limit_checkbox, row=5, column=1, width=4, height=1)

        # Enable Output Limit checkbox
        self.v_enable_output_limit_checkbox = CheckboxWidget(
            widget_id='v_enable_output_limit',
            value=False,
            title='Out-Limit:',
            title_position='left',
        )
        v_pid_group.addWidget(self.v_enable_output_limit_checkbox, row=5, column=5, width=4, height=1)

        # Enable D-Filter checkbox
        self.v_enable_d_filter_checkbox = CheckboxWidget(
            widget_id='v_enable_d_filter',
            value=False,
            title='D-Filter:',
            title_position='left',
        )
        v_pid_group.addWidget(self.v_enable_d_filter_checkbox, row=5, column=9, width=4, height=1)

        # Kv feedforward dial (smaller)
        self.v_kv_dial = RotaryDialWidget(
            widget_id='v_kv_dial',
            min_value=-0.5,
            max_value=0.0,
            increment=0.01,
            value=-0.1,
            title='Kv (FF)',
            continuousUpdates=False,
            dialColor=[0.2, 0.7, 0.5, 1.0],
        )
        v_pid_group.addWidget(self.v_kv_dial, row=6, column=1, width=4, height=3)

        def on_v_kv_changed(value, *args, **kwargs):
            # TODO: Add method to set feedforward Kv
            self.logger.debug(f"Forward Kv changed to {value}")

        self.v_kv_dial.callbacks.value_changed.register(on_v_kv_changed)

        # Reset to defaults button
        self.v_reset_button = Button(
            widget_id='v_reset_button',
            text='Reset to Default',
            color=[0.5, 0.3, 0.2],
        )
        v_pid_group.addWidget(self.v_reset_button, row=6, column=5, width=8, height=2)

        def on_v_reset_clicked(*args, **kwargs):
            self.logger.info("Resetting forward velocity PID to defaults")
            self.robot.control.load_default_control_config()

        self.v_reset_button.callbacks.click.register(on_v_reset_clicked)

        # Turn Rate (Psi Dot) PID Group
        psidot_pid_group = Widget_Group(
            group_id='psidot_pid_group',
            title='Velocity PID (Turn)',
            rows=8,
            columns=12,
            show_title=True
        )
        page.addWidget(psidot_pid_group, column=17, row=10, width=12, height=9)

        # Kp dial for turn rate (typical range: 0 to 0.1, default: 0.01)
        self.psidot_kp_dial = RotaryDialWidget(
            widget_id='psidot_kp_dial',
            min_value=0.0,
            max_value=0.1,
            increment=0.001,
            value=0.01,
            title='Kp',
            continuousUpdates=False,
            dialColor=[0.2, 0.5, 0.8, 1.0],
        )
        psidot_pid_group.addWidget(self.psidot_kp_dial, row=1, column=1, width=4, height=4)

        def on_psidot_kp_changed(value, *args, **kwargs):
            self.robot.control.set_turn_pid(P=value)

        self.psidot_kp_dial.callbacks.value_changed.register(on_psidot_kp_changed)

        # Ki dial for turn rate (typical range: 0 to 1, default: 0.05)
        self.psidot_ki_dial = RotaryDialWidget(
            widget_id='psidot_ki_dial',
            min_value=0.0,
            max_value=1.0,
            increment=0.01,
            value=0.05,
            title='Ki',
            continuousUpdates=False,
            dialColor=[0.5, 0.2, 0.8, 1.0],
        )
        psidot_pid_group.addWidget(self.psidot_ki_dial, row=1, column=5, width=4, height=4)

        def on_psidot_ki_changed(value, *args, **kwargs):
            self.robot.control.set_turn_pid(I=value)

        self.psidot_ki_dial.callbacks.value_changed.register(on_psidot_ki_changed)

        # Kd dial for turn rate (negative only: -0.01 to 0, default: 0)
        self.psidot_kd_dial = RotaryDialWidget(
            widget_id='psidot_kd_dial',
            min_value=-0.01,
            max_value=0.0,
            increment=0.0001,
            value=0.0,
            title='Kd',
            continuousUpdates=False,
            dialColor=[0.8, 0.5, 0.2, 1.0],
        )
        psidot_pid_group.addWidget(self.psidot_kd_dial, row=1, column=9, width=4, height=4)

        def on_psidot_kd_changed(value, *args, **kwargs):
            self.robot.control.set_turn_pid(D=value)

        self.psidot_kd_dial.callbacks.value_changed.register(on_psidot_kd_changed)

        # Enable I-Limit checkbox
        self.psidot_enable_i_limit_checkbox = CheckboxWidget(
            widget_id='psidot_enable_i_limit',
            value=False,
            title='I-Limit:',
            title_position='left',
        )
        psidot_pid_group.addWidget(self.psidot_enable_i_limit_checkbox, row=5, column=1, width=4, height=1)

        # Enable Output Limit checkbox
        self.psidot_enable_output_limit_checkbox = CheckboxWidget(
            widget_id='psidot_enable_output_limit',
            value=False,
            title='Out-Limit:',
            title_position='left',
        )
        psidot_pid_group.addWidget(self.psidot_enable_output_limit_checkbox, row=5, column=5, width=4, height=1)

        # Enable D-Filter checkbox
        self.psidot_enable_d_filter_checkbox = CheckboxWidget(
            widget_id='psidot_enable_d_filter',
            value=False,
            title='D-Filter:',
            title_position='left',
        )
        psidot_pid_group.addWidget(self.psidot_enable_d_filter_checkbox, row=5, column=9, width=4, height=1)

        # Kv feedforward dial for turn (smaller)
        self.psidot_kv_dial = RotaryDialWidget(
            widget_id='psidot_kv_dial',
            min_value=0.0,
            max_value=0.5,
            increment=0.01,
            value=0.1,
            title='Kv (FF)',
            continuousUpdates=False,
            dialColor=[0.2, 0.7, 0.5, 1.0],
        )
        psidot_pid_group.addWidget(self.psidot_kv_dial, row=6, column=1, width=4, height=3)

        def on_psidot_kv_changed(value, *args, **kwargs):
            # TODO: Add method to set feedforward Kv for turn
            self.logger.debug(f"Turn Kv changed to {value}")

        self.psidot_kv_dial.callbacks.value_changed.register(on_psidot_kv_changed)

        # Reset to defaults button for turn PID
        self.psidot_reset_button = Button(
            widget_id='psidot_reset_button',
            text='Reset to Default',
            color=[0.5, 0.3, 0.2],
        )
        psidot_pid_group.addWidget(self.psidot_reset_button, row=6, column=5, width=8, height=2)

        def on_psidot_reset_clicked(*args, **kwargs):
            self.logger.info("Resetting turn velocity PID to defaults")
            self.robot.control.load_default_control_config()

        self.psidot_reset_button.callbacks.click.register(on_psidot_reset_clicked)

        # === CONTROL CONFIG TABLE ===
        self.control_config_table = Table(widget_id='control_config_table')
        self.control_config_table.add_column(
            TextColumn(id='parameter', title='Parameter', width=0.5, font_align='left'))
        self.control_config_table.add_column(TextColumn(id='value', title='Value', width=0.5, font_align='right'))

        # Create table groups for organization
        self.config_general_group = TableGroup(
            id='config_general',
            title='General',
            collapsible=True,
            group_color=[0.3, 0.3, 0.5, 0.9]
        )
        self.control_config_table.items[self.config_general_group.id] = self.config_general_group
        self.config_general_group._table = self.control_config_table

        self.config_velocity_v_group = TableGroup(
            id='config_velocity_v',
            title='Velocity Control (Forward)',
            collapsible=True,
            group_color=[0.2, 0.5, 0.3, 0.9]
        )
        self.control_config_table.items[self.config_velocity_v_group.id] = self.config_velocity_v_group
        self.config_velocity_v_group._table = self.control_config_table

        self.config_velocity_psidot_group = TableGroup(
            id='config_velocity_psidot',
            title='Velocity Control (Turn)',
            collapsible=True,
            group_color=[0.5, 0.3, 0.2, 0.9]
        )
        self.control_config_table.items[self.config_velocity_psidot_group.id] = self.config_velocity_psidot_group
        self.config_velocity_psidot_group._table = self.control_config_table

        # Create placeholder rows that will be updated
        self.config_rows = {}

        # General config rows
        self.config_rows['max_wheel_speed'] = self.config_general_group.make_row(parameter='Max Wheel Speed',
                                                                                 value='0.0')
        self.config_rows['max_wheel_torque'] = self.config_general_group.make_row(parameter='Max Wheel Torque',
                                                                                  value='0.0')
        self.config_rows['enable_external_inputs'] = self.config_general_group.make_row(parameter='External Inputs',
                                                                                        value='disabled')

        # Velocity V PID rows
        self.config_rows['v_kp'] = self.config_velocity_v_group.make_row(parameter='Kp', value='0.0')
        self.config_rows['v_ki'] = self.config_velocity_v_group.make_row(parameter='Ki', value='0.0')
        self.config_rows['v_kd'] = self.config_velocity_v_group.make_row(parameter='Kd', value='0.0')
        self.config_rows['v_kv'] = self.config_velocity_v_group.make_row(parameter='Kv (FF)', value='0.0')
        self.config_rows['v_ka'] = self.config_velocity_v_group.make_row(parameter='Ka (FF)', value='0.0')
        self.config_rows['v_i_term_limit'] = self.config_velocity_v_group.make_row(parameter='I-Term Limit',
                                                                                   value='0.0 (disabled)')
        self.config_rows['v_output_limit'] = self.config_velocity_v_group.make_row(parameter='Output Limit',
                                                                                   value='0.0 (disabled)')
        self.config_rows['v_d_filter'] = self.config_velocity_v_group.make_row(parameter='D-Filter Td',
                                                                               value='0.0 (disabled)')

        # Velocity Psidot PID rows
        self.config_rows['psidot_kp'] = self.config_velocity_psidot_group.make_row(parameter='Kp', value='0.0')
        self.config_rows['psidot_ki'] = self.config_velocity_psidot_group.make_row(parameter='Ki', value='0.0')
        self.config_rows['psidot_kd'] = self.config_velocity_psidot_group.make_row(parameter='Kd', value='0.0')
        self.config_rows['psidot_kv'] = self.config_velocity_psidot_group.make_row(parameter='Kv (FF)', value='0.0')
        self.config_rows['psidot_ka'] = self.config_velocity_psidot_group.make_row(parameter='Ka (FF)', value='0.0')
        self.config_rows['psidot_i_term_limit'] = self.config_velocity_psidot_group.make_row(parameter='I-Term Limit',
                                                                                             value='0.0 (disabled)')
        self.config_rows['psidot_output_limit'] = self.config_velocity_psidot_group.make_row(parameter='Output Limit',
                                                                                             value='0.0 (disabled)')
        self.config_rows['psidot_d_filter'] = self.config_velocity_psidot_group.make_row(parameter='D-Filter Td',
                                                                                         value='0.0 (disabled)')

        page.addWidget(self.control_config_table, column=30, row=1, width=20, height=16)

        # Initialize values from actual robot config
        self._initialize_control_widgets_from_config()

        # Start periodic update of the control config table
        self._start_control_config_update()

    # ------------------------------------------------------------------------------------------------------------------
    def build_debug_page(self, page):
        """Build the Debug page for temporary/experimental features."""

        # === ESTIMATION DEBUG GROUP ===
        estimation_group = Widget_Group(
            group_id='estimation_debug',
            title='Estimation',
            rows=6,
            columns=12,
            show_title=True
        )
        page.addWidget(estimation_group, column=1, row=1, width=12, height=7)

        # Dead-reckoning toggle button
        self.dead_reckoning_button = MultiStateButton(
            id='dead_reckoning_toggle',
            states=['ON', 'OFF'],
            current_state='ON',
            color=[
                [0.2, 0.6, 0.2],  # Green for ON
                [0.6, 0.3, 0.2],  # Red for OFF
            ],
            title='Dead Reckoning EKF'
        )
        estimation_group.addWidget(self.dead_reckoning_button, row=1, column=1, width=12, height=2)

        def on_dead_reckoning_toggle(state, *args, **kwargs):
            enable = (state == 'OFF')  # If currently OFF, enable it
            self.robot.estimation.set_dead_reckoning_enabled(enable)
            # Toggle to opposite state
            new_state = 'ON' if enable else 'OFF'
            self.dead_reckoning_button.state = new_state

        self.dead_reckoning_button.callbacks.click.register(on_dead_reckoning_toggle)

        # Tracker updates toggle button (simulate tracker unavailable)
        self.tracker_updates_button = MultiStateButton(
            id='tracker_updates_toggle',
            states=['ON', 'OFF'],
            current_state='ON',
            color=[
                [0.2, 0.6, 0.2],  # Green for ON
                [0.6, 0.3, 0.2],  # Red for OFF
            ],
            title='Tracker → Lowlevel'
        )
        estimation_group.addWidget(self.tracker_updates_button, row=3, column=1, width=12, height=2)

        def on_tracker_updates_toggle(state, *args, **kwargs):
            enable = (state == 'OFF')  # If currently OFF, enable it
            self.robot.estimation.set_tracker_updates_enabled(enable)
            # Toggle to opposite state
            new_state = 'ON' if enable else 'OFF'
            self.tracker_updates_button.state = new_state

        self.tracker_updates_button.callbacks.click.register(on_tracker_updates_toggle)

        # Initialize from robot state (delayed to allow connection)
        def init_estimation_debug_state():
            try:
                # Dead-reckoning state
                dr_enabled = self.robot.estimation.get_dead_reckoning_enabled()
                if dr_enabled is not None:
                    self.dead_reckoning_button.state = 'ON' if dr_enabled else 'OFF'

                # Tracker updates state
                tracker_enabled = self.robot.estimation.get_tracker_updates_enabled()
                if tracker_enabled is not None:
                    self.tracker_updates_button.state = 'ON' if tracker_enabled else 'OFF'
            except Exception as e:
                self.logger.warning(f"Could not get estimation debug state: {e}")

        set_timeout(init_estimation_debug_state, 1.0)

    # ------------------------------------------------------------------------------------------------------------------
    def build_folder(self):
        self.app_folder = Folder(folder_id=self.robot.id, rows=3, columns=8)
        self.app_folder.addPage(FolderPage(
            page_id='control',
            rows=2, columns=8
        ))

        # Test Joystick Widget
        joystick_forward = JoystickWidget(
            widget_id='joystick_forward',
            title='Forward',
            fixed_axis='vertical',
            return_to_center=True,
            continuous_updates=True,
            max_updates_per_second=20,
            show_values=True,
            deadzone=0.05,
        )

        # def on_joystick_position_changed(x, y):
        #     self.logger.info(f"Joystick position: x={x:.2f}, y={y:.2f}")
        #
        # joystick_forward.callbacks.position_changed.register(on_joystick_position_changed)
        self.app_folder.addObject(joystick_forward, width=3, height=3, column=1, row=1)

        joystick_turn = JoystickWidget(
            widget_id='joystick_turn',
            title='Turn',
            fixed_axis='horizontal',
            return_to_center=True,
            continuous_updates=True,
            max_updates_per_second=20,
            show_values=True,
            deadzone=0.05,
        )

        # joystick_turn.callbacks.position_changed.register(on_joystick_position_changed)
        self.app_folder.addObject(joystick_turn, width=3, height=3, column=6, row=1)

        self.app_bilbo_mode_widget = BilboModeWidget(widget_id='bilbo_mode_widget',
                                                     title='Bilbo Mode',
                                                     current_mode=self.robot.control.mode.name)
        self.app_folder.addObject(self.app_bilbo_mode_widget, width=2, height=1, column=4, row=1)

        def update_mode_widget(mode: BILBO_Control_Mode, *args, **kwargs):
            self.app_bilbo_mode_widget.current_mode = mode.name

        def mode_widget_click_callback(mode_id, *args, **kwargs):
            match mode_id:
                case 'OFF':
                    self.robot.control.setControlMode(BILBO_Control_Mode.OFF)
                case 'DIRECT':
                    self.robot.control.setControlMode(BILBO_Control_Mode.DIRECT)
                case 'POSITION':
                    self.robot.control.setControlMode(BILBO_Control_Mode.POSITION)
                case 'VELOCITY':
                    self.robot.control.setControlMode(BILBO_Control_Mode.VELOCITY)
                case 'BALANCING':
                    self.robot.control.setControlMode(BILBO_Control_Mode.BALANCING)

        self.app_bilbo_mode_widget.callbacks.mode_clicked.register(mode_widget_click_callback)
        self.robot.control.events.mode_changed.on(update_mode_widget)

        joystick_forward.disable()
        joystick_turn.disable()

        def joystick_enable_clicked(*args, **kwargs):

            if self.robot.interfaces.app_joystick_widgets is not None:
                joystick_forward.disable()
                joystick_turn.disable()
                self.robot.interfaces.app_joystick_widgets = None
                joystick_enable_button.updateConfig(text="Enable Joysticks")
            else:
                joystick_forward.enable(True)
                joystick_turn.enable(True)
                self.robot.interfaces.set_app_joystick_widgets({
                    'forward': joystick_forward,
                    'turn': joystick_turn,
                })
                joystick_enable_button.updateConfig(text="Disable Joysticks")

        joystick_enable_button = Button(widget_id='joystick_enable_button',
                                        text='Enable Joysticks',
                                        color=[0.5, 0.3, 0.2],
                                        callback=joystick_enable_clicked)

        self.app_folder.addObject(joystick_enable_button, width=1, height=1, column=4)

        self.app.addFolder(self.app_folder)

    # ------------------------------------------------------------------------------------------------------------------
    def on_robot_stream(self, sample: BILBO_Sample, *args, **kwargs):
        if not self._built:
            return

        if self.robot.core.tick % 100 == 0:
            # Check the static state
            robot_is_static = sample.estimation.static
            if robot_is_static:
                self.control_status_widget.elements['static'].status = 'true'
                self.control_status_widget.elements['static'].color = [0, 0.6, 0]
            else:
                self.control_status_widget.elements['static'].status = 'false'
                self.control_status_widget.elements['static'].color = [0.6, 0.4, 0.0]
            self.control_status_widget.updateConfig()

            if sample.control.vic_enabled:
                self.control_status_widget.elements['vic'].status = 'enabled'
                self.control_status_widget.elements['vic'].color = [0, 0.5, 0]
            else:
                self.control_status_widget.elements['vic'].status = 'disabled'
                self.control_status_widget.elements['vic'].color = [0.5, 0.5, 0.5]
            self.control_status_widget.updateConfig()

            # Update estimation status (dead-reckoning vs tracked)
            is_dead_reckoning = sample.estimation.is_dead_reckoning
            if is_dead_reckoning:
                self.estimation_status_widget.elements['tracking'].status = 'Dead-Reckoning'
                self.estimation_status_widget.elements['tracking'].color = [0.6, 0.2, 0.2]  # Red
            else:
                self.estimation_status_widget.elements['tracking'].status = 'Tracked'
                self.estimation_status_widget.elements['tracking'].color = [0.2, 0.6, 0.2]  # Green
            self.estimation_status_widget.updateConfig()

        if self.robot.core.tick % 200 == 0:
            # Update the overview widgets
            voltage = sample.sensors.power.bat_voltage
            cells = self.robot.config.electronics.battery_cells
            self.battery_indicator.setValue(percentage=lipo_soc(voltage=voltage, cells=cells), voltage=voltage)

            # Connection
            self.connection_strength_indicator.setValue(
                'high' if sample.general.connection_strength > 85 else
                'medium' if sample.general.connection_strength > 30 else
                'low'
            )

            # Internet
            self.internet_indicator.setValue(sample.general.internet_connected)

            # Joystick assigned?
            # if js_control is not None:
            #     self.joystick_indicator.setValue(js_control.robotIsAssigned(self.robot) is not None)
            # else:
            #     self.joystick_indicator.setValue(False)

        # Update the states digital numbers
        self.x_digital_number.value = sample.estimation.state.x
        self.y_digital_number.value = sample.estimation.state.y
        self.v_digital_number.value = sample.estimation.state.v

        self.theta_digital_number.value = np.rad2deg(sample.estimation.state.theta) if self.overview_page_data[
                                                                                           'theta_digital_number_format'] == 'grad' else sample.estimation.state.theta
        self.theta_dot_digital_number.value = np.rad2deg(sample.estimation.state.theta_dot) if self.overview_page_data[
                                                                                                   'theta_dot_digital_number_format'] == 'grad' else sample.estimation.state.theta_dot
        self.psi_digital_number.value = (sample.estimation.state.psi) if self.overview_page_data[
                                                                             'psi_digital_number_format'] == 'rad' else np.rad2deg(
            sample.estimation.state.psi)
        self.psi_dot_digital_number.value = (sample.estimation.state.psi_dot) if self.overview_page_data[
                                                                                     'psi_dot_digital_number_format'] == 'rad' else np.rad2deg(
            sample.estimation.state.psi_dot)

        # Update gyro readings (convert to deg/s)
        self.gyro_x_number.value = np.rad2deg(sample.lowlevel.sensors.gyr.x)
        self.gyro_y_number.value = np.rad2deg(sample.lowlevel.sensors.gyr.y)
        self.gyro_z_number.value = np.rad2deg(sample.lowlevel.sensors.gyr.z)

        # Update accelerometer readings
        self.acc_x_number.value = sample.lowlevel.sensors.acc.x
        self.acc_y_number.value = sample.lowlevel.sensors.acc.y
        self.acc_z_number.value = sample.lowlevel.sensors.acc.z

        self.timeseries_v.set_value(sample.estimation.state.v)
        self.timeseries_theta.set_value(np.rad2deg(sample.estimation.state.theta))
        self.theta_dot_timeseries.set_value(np.rad2deg(sample.estimation.state.theta_dot))
        self.psi_plot_timeseries.set_value(np.rad2deg(sample.estimation.state.psi))
        self.psi_dot_timeseries.set_value(np.rad2deg(sample.estimation.state.psi_dot))
        self.x_timeseries.set_value(sample.estimation.state.x)
        self.y_timeseries.set_value(sample.estimation.state.y)

        self.input_left_timeseries.set_value(sample.lowlevel.control.output.u_left)
        self.input_right_timeseries.set_value(sample.lowlevel.control.output.u_right)

        # Update map agent position from robot estimation state
        tick = self.robot.core.tick
        if self._first_stream_tick is None:
            self._first_stream_tick = tick
        if (tick - self._first_stream_tick) % 5 == 0:
            self.robot_map_agent.update(
                x=sample.estimation.state.x,
                y=sample.estimation.state.y,
                psi=sample.estimation.state.psi
            )

            # Change agent color based on tracking source
            is_tracked = not sample.estimation.is_dead_reckoning
            if is_tracked != self._agent_is_tracked:
                self._agent_is_tracked = is_tracked
                color = [0.2, 0.6, 0.2] if is_tracked else [0.6, 0.2, 0.2]
                self.robot_map_agent.updateConfig(color=color)

    # ------------------------------------------------------------------------------------------------------------------
    def on_new_tracker_sample(self, sample, *args, **kwargs):
        if not self._built:
            return

        # Update obstacle positions on map
        for obs_id, map_obj in self._obstacle_map_objects.items():
            if obs_id in self.manager.testbed.obstacles:
                obs = self.manager.testbed.obstacles[obs_id]
                s = obs.state
                map_obj.update(x=s.x, y=s.y, psi=s.psi)

    # ------------------------------------------------------------------------------------------------------------------
    def on_control_mode_changed(self, mode: BILBO_Control_Mode, *args, **kwargs):
        if not self._built:
            return
        # Overview Status Widget
        self.general_status_widget.elements['mode'].status = mode.name
        self.general_status_widget.elements['mode'].color = CONTROL_MODE_COLORS[mode]
        self.general_status_widget.updateConfig()

        self.control_status_widget.elements['mode'].status = mode.name
        self.control_status_widget.elements['mode'].color = CONTROL_MODE_COLORS[mode]
        self.control_status_widget.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def on_tic_mode_changed(self, mode: bool, *args, **kwargs):
        self.control_status_widget.elements['tic'].status = 'enabled' if mode else 'disabled'
        self.control_status_widget.elements['tic'].color = [0, 0.5, 0] if mode else [0.5, 0.5, 0.5]
        self.control_status_widget.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def on_vic_mode_changed(self, mode: bool):
        self.control_status_widget.elements['vic'].status = 'enabled' if mode else 'disabled'
        self.control_status_widget.elements['vic'].color = [0, 0.5, 0] if mode else [0.5, 0.5, 0.5]
        self.control_status_widget.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def on_dilc_experiment_initialized(self, data, *args, **kwargs):
        self.logger.info("DILC experiment initialized — opening DILC app")
        dilc_experiment = data.get('experiment')
        if dilc_experiment is None:
            self.logger.error("No DILC experiment handle in event data")
            return
        self.dilc_app = DILC_APP(
            gui=self.gui,
            robot=self.robot,
            experiment=dilc_experiment,
        )
        self.dilc_app.open(self.gui)

    # ------------------------------------------------------------------------------------------------------------------
    def _initialize_control_widgets_from_config(self):
        """Initialize dials and checkboxes with actual values from robot control config."""
        try:
            config = self.robot.control.get_control_config()
            if config is None:
                self.logger.warning("Could not read control config for initialization")
                return

            # Initialize forward velocity PID dials
            self.v_kp_dial._value = config.velocity_control.v.pid.Kp
            self.v_ki_dial._value = config.velocity_control.v.pid.Ki
            self.v_kd_dial._value = config.velocity_control.v.pid.Kd
            self.v_kv_dial._value = config.velocity_control.v.feedforward.Kv

            # Initialize turn velocity PID dials
            self.psidot_kp_dial._value = config.velocity_control.psidot.pid.Kp
            self.psidot_ki_dial._value = config.velocity_control.psidot.pid.Ki
            self.psidot_kd_dial._value = config.velocity_control.psidot.pid.Kd
            self.psidot_kv_dial._value = config.velocity_control.psidot.feedforward.Kv

            # Initialize forward velocity checkboxes
            self.v_enable_i_limit_checkbox._value = config.velocity_control.v.pid.enable_i_limit
            self.v_enable_output_limit_checkbox._value = config.velocity_control.v.pid.enable_output_limit
            self.v_enable_d_filter_checkbox._value = config.velocity_control.v.pid.enable_d_filter

            # Initialize turn velocity checkboxes
            self.psidot_enable_i_limit_checkbox._value = config.velocity_control.psidot.pid.enable_i_limit
            self.psidot_enable_output_limit_checkbox._value = config.velocity_control.psidot.pid.enable_output_limit
            self.psidot_enable_d_filter_checkbox._value = config.velocity_control.psidot.pid.enable_d_filter

            self.logger.debug("Initialized control widgets from robot config")

        except Exception as e:
            self.logger.warning(f"Failed to initialize control widgets from config: {e}")

    # ------------------------------------------------------------------------------------------------------------------
    def _start_control_config_update(self):
        """Start periodic update of the control config table every 1 second."""
        return
        self._control_config_timer = None

        def update_config():
            self._update_control_config_table()

        self._control_config_timer = setInterval(update_config, 1.0)

    # ------------------------------------------------------------------------------------------------------------------
    def _format_value_with_enable(self, value: float, enabled: bool, precision: int = 4) -> str:
        """Format a numeric value with enable status as text."""
        status = 'enabled' if enabled else 'disabled'
        return f"{value:.{precision}f} ({status})"

    # ------------------------------------------------------------------------------------------------------------------
    def _update_control_config_table(self):
        """Fetch current control config from robot and update table values."""
        try:
            # Get the full control config from the robot
            config = self.robot.control.get_control_config()
            if config is None:
                return

            # Update general config values (as formatted text)
            self.config_rows['max_wheel_speed']['value'] = f"{config.general.max_wheel_speed:.2f}"
            self.config_rows['max_wheel_torque']['value'] = f"{config.general.max_wheel_torque:.3f}"
            self.config_rows['enable_external_inputs'][
                'value'] = 'enabled' if config.general.enable_external_inputs else 'disabled'

            # Update velocity forward (v) PID values (as formatted text)
            self.config_rows['v_kp']['value'] = f"{config.velocity_control.v.pid.Kp:.4f}"
            self.config_rows['v_ki']['value'] = f"{config.velocity_control.v.pid.Ki:.4f}"
            self.config_rows['v_kd']['value'] = f"{config.velocity_control.v.pid.Kd:.4f}"
            self.config_rows['v_kv']['value'] = f"{config.velocity_control.v.feedforward.Kv:.4f}"
            self.config_rows['v_ka']['value'] = f"{config.velocity_control.v.feedforward.Ka:.4f}"
            self.config_rows['v_i_term_limit']['value'] = self._format_value_with_enable(
                config.velocity_control.v.pid.i_term_limit, config.velocity_control.v.pid.enable_i_limit)
            self.config_rows['v_output_limit']['value'] = self._format_value_with_enable(
                config.velocity_control.v.pid.output_limit, config.velocity_control.v.pid.enable_output_limit)
            self.config_rows['v_d_filter']['value'] = self._format_value_with_enable(
                config.velocity_control.v.pid.Td_filter, config.velocity_control.v.pid.enable_d_filter)

            # Update velocity turn (psidot) PID values (as formatted text)
            self.config_rows['psidot_kp']['value'] = f"{config.velocity_control.psidot.pid.Kp:.4f}"
            self.config_rows['psidot_ki']['value'] = f"{config.velocity_control.psidot.pid.Ki:.4f}"
            self.config_rows['psidot_kd']['value'] = f"{config.velocity_control.psidot.pid.Kd:.4f}"
            self.config_rows['psidot_kv']['value'] = f"{config.velocity_control.psidot.feedforward.Kv:.4f}"
            self.config_rows['psidot_ka']['value'] = f"{config.velocity_control.psidot.feedforward.Ka:.4f}"
            self.config_rows['psidot_i_term_limit']['value'] = self._format_value_with_enable(
                config.velocity_control.psidot.pid.i_term_limit, config.velocity_control.psidot.pid.enable_i_limit)
            self.config_rows['psidot_output_limit']['value'] = self._format_value_with_enable(
                config.velocity_control.psidot.pid.output_limit, config.velocity_control.psidot.pid.enable_output_limit)
            self.config_rows['psidot_d_filter']['value'] = self._format_value_with_enable(
                config.velocity_control.psidot.pid.Td_filter, config.velocity_control.psidot.pid.enable_d_filter)

            # Update the dial widgets to reflect current values
            # Only update if significantly different to avoid feedback loops
            if abs(self.v_kp_dial.value - config.velocity_control.v.pid.Kp) > 0.0001:
                self.v_kp_dial._value = config.velocity_control.v.pid.Kp
                self.v_kp_dial._sendValueToFrontend(self.v_kp_dial._value)
            if abs(self.v_ki_dial.value - config.velocity_control.v.pid.Ki) > 0.001:
                self.v_ki_dial._value = config.velocity_control.v.pid.Ki
                self.v_ki_dial._sendValueToFrontend(self.v_ki_dial._value)
            if abs(self.v_kd_dial.value - config.velocity_control.v.pid.Kd) > 0.00001:
                self.v_kd_dial._value = config.velocity_control.v.pid.Kd
                self.v_kd_dial._sendValueToFrontend(self.v_kd_dial._value)
            if abs(self.v_kv_dial.value - config.velocity_control.v.feedforward.Kv) > 0.001:
                self.v_kv_dial._value = config.velocity_control.v.feedforward.Kv
                self.v_kv_dial._sendValueToFrontend(self.v_kv_dial._value)

            if abs(self.psidot_kp_dial.value - config.velocity_control.psidot.pid.Kp) > 0.0001:
                self.psidot_kp_dial._value = config.velocity_control.psidot.pid.Kp
                self.psidot_kp_dial._sendValueToFrontend(self.psidot_kp_dial._value)
            if abs(self.psidot_ki_dial.value - config.velocity_control.psidot.pid.Ki) > 0.001:
                self.psidot_ki_dial._value = config.velocity_control.psidot.pid.Ki
                self.psidot_ki_dial._sendValueToFrontend(self.psidot_ki_dial._value)
            if abs(self.psidot_kd_dial.value - config.velocity_control.psidot.pid.Kd) > 0.00001:
                self.psidot_kd_dial._value = config.velocity_control.psidot.pid.Kd
                self.psidot_kd_dial._sendValueToFrontend(self.psidot_kd_dial._value)
            if abs(self.psidot_kv_dial.value - config.velocity_control.psidot.feedforward.Kv) > 0.001:
                self.psidot_kv_dial._value = config.velocity_control.psidot.feedforward.Kv
                self.psidot_kv_dial._sendValueToFrontend(self.psidot_kv_dial._value)

            # Update checkbox widgets to reflect current values
            if self.v_enable_i_limit_checkbox._value != config.velocity_control.v.pid.enable_i_limit:
                self.v_enable_i_limit_checkbox._value = config.velocity_control.v.pid.enable_i_limit
                self.v_enable_i_limit_checkbox._sendValueToFrontend(self.v_enable_i_limit_checkbox._value)
            if self.v_enable_output_limit_checkbox._value != config.velocity_control.v.pid.enable_output_limit:
                self.v_enable_output_limit_checkbox._value = config.velocity_control.v.pid.enable_output_limit
                self.v_enable_output_limit_checkbox._sendValueToFrontend(self.v_enable_output_limit_checkbox._value)
            if self.v_enable_d_filter_checkbox._value != config.velocity_control.v.pid.enable_d_filter:
                self.v_enable_d_filter_checkbox._value = config.velocity_control.v.pid.enable_d_filter
                self.v_enable_d_filter_checkbox._sendValueToFrontend(self.v_enable_d_filter_checkbox._value)

            if self.psidot_enable_i_limit_checkbox._value != config.velocity_control.psidot.pid.enable_i_limit:
                self.psidot_enable_i_limit_checkbox._value = config.velocity_control.psidot.pid.enable_i_limit
                self.psidot_enable_i_limit_checkbox._sendValueToFrontend(self.psidot_enable_i_limit_checkbox._value)
            if self.psidot_enable_output_limit_checkbox._value != config.velocity_control.psidot.pid.enable_output_limit:
                self.psidot_enable_output_limit_checkbox._value = config.velocity_control.psidot.pid.enable_output_limit
                self.psidot_enable_output_limit_checkbox._sendValueToFrontend(
                    self.psidot_enable_output_limit_checkbox._value)
            if self.psidot_enable_d_filter_checkbox._value != config.velocity_control.psidot.pid.enable_d_filter:
                self.psidot_enable_d_filter_checkbox._value = config.velocity_control.psidot.pid.enable_d_filter
                self.psidot_enable_d_filter_checkbox._sendValueToFrontend(self.psidot_enable_d_filter_checkbox._value)

        except Exception as e:
            self.logger.warning(f"Failed to update control config table: {e}")
            try:
                self._control_config_timer.stop()
            except Exception:
                pass

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        # Cancel the control config update timer
        if hasattr(self, '_control_config_timer') and self._control_config_timer is not None:
            try:
                self._control_config_timer.stop()
            except Exception:
                pass

        try:
            self.gui.categories['robots'].removeCategory(self.category)
        except Exception:
            pass

        # try:
        #     self.app.removeFolder(self.folder)
        # except Exception:
        #     pass

        for plot in self.plots:
            # plot.
            ...
        self.map_widget.onDelete()


