import dataclasses
import time
from random import randint, random, uniform
from typing import Dict, Optional, Callable

import numpy as np
from qmt import wrapToPi

from core.utils.uuid_utils import generate_uuid
from extensions.gui.src.lib.objects.python.bilbo_mode import BilboModeWidget
from extensions.gui.src.lib.objects.python.joystick_assignment import JoystickAssignmentWidget
# === CUSTOM MODULES ===================================================================================================
from robots.bilbo.gui.applications.dilc_app import DILC_APP
from robots.bilbo.gui.applications.input_viewer import InputViewerApplication
from robots.bilbo.robot.bilbo_position_control import (
    MoveToPointCommand, TurnToHeadingCommand, PathData
)
from robots.bilbo.testbed.testbed_manager import TestbedManager, TestbedManagerSettings
from robots.bilbo.testbed.objects import TestbedBILBO, RealTestbedBILBO
from core.utils.callbacks import callback_definition, CallbackContainer, Callback
from core.utils.colors import get_color_from_palette, random_color_from_palette, get_palette
from core.utils.lipo import lipo_soc
from core.utils.logging_utils import Logger, addLogRedirection, LOGGING_COLORS
from core.utils.time import setTimeout, set_timeout, setInterval
from core.utils.timecode.timecode import Timecode
from core.utils.timecode.timecode_server import TimecodeServerStatus
from extensions.babylon.src.babylon import BabylonVisualization
from extensions.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo
from extensions.babylon.src.lib.objects.box.box import Box, WallFancy
from extensions.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.cli.cli import CLI
from extensions.gui.src.app import App, Folder, FolderPage
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.map.map import MapWidget
from extensions.gui.src.lib.map.map_objects import Agent, Point, Line, Circle, Rectangle, MapObject
from extensions.gui.src.lib.objects.objects import Widget_Group, ContextMenuItem, ContextMenuGroup
from extensions.gui.src.lib.objects.python.babylon_widget import BabylonWidget
from extensions.gui.src.lib.objects.python.buttons import MultiStateButton, Button
from extensions.gui.src.lib.objects.python.callout import CalloutType, CalloutButton
from extensions.gui.src.lib.objects.python.indicators import BatteryIndicatorWidget, ConnectionIndicator, \
    InternetIndicator, JoystickIndicator, ProgressIndicator, CircleIndicator
from extensions.gui.src.lib.objects.python.number import DigitalNumberWidget, DigitalClockWidget
from extensions.gui.src.lib.objects.python.popup import YesNoPopup, Popup
from extensions.gui.src.lib.objects.python.table import Table, TextColumn, IndicatorColumn, NumberColumn, TableGroup, \
    CheckboxColumn
from extensions.gui.src.lib.objects.python.dial import RotaryDialWidget
from extensions.gui.src.lib.objects.python.checkbox import CheckboxWidget
from extensions.gui.src.lib.objects.python.text_input import InputWidget
from extensions.gui.src.lib.objects.python.sliders import ClassicSliderWidget
from extensions.gui.src.lib.objects.python.joystick import JoystickWidget
from extensions.gui.src.lib.objects.python.text import TextWidget, StatusWidget, StatusWidgetElement
from extensions.gui.src.lib.plot.realtime.rt_plot import ServerMode, UpdateMode, TimeSeries, RT_Plot_Widget
from extensions.joystick.joystick_manager import Joystick
from robots.bilbo.manager.bilbo_joystick_control import BILBO_JoystickControl
from robots.bilbo.robot.bilbo import BILBO
from robots.bilbo.robot.bilbo_data import BILBO_Sample
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode
from robots.bilbo.robot.bilbo_utilities import CONTROL_MODE_COLORS
from robots.bilbo.robot.experiment.bilbo_experiment import BILBO_ExperimentHandler_Status
from robots.bilbo.robot.experiment.experiment_definitions import BILBO_InputTrajectory
from robots.bilbo.robot.experiment.multi_trial_experiments import DILC_Experiment
# TestbedBILBO and RealTestbedBILBO imported above from testbed.objects
from core.utils.mdns import MDNSAdvertiser
from core.utils.network.port_forwarder import PortForwarder
from extensions.gui.settings import PORT_JS_APP

# from robots.bilbo.robot.experiment.experiments import DILC_Experiment

# mDNS settings - advertise bilbolab.local on the network
MDNS_HOSTNAME = "bilbolab"  # Will be accessible as http://bilbolab.local/gui (with port 80) or :8400/gui

# === GLOBAL VARIABLES =================================================================================================
js_control: Optional[BILBO_JoystickControl] = None

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

        # Register some events
        self.robot.experiment_handler.events.dilc_experiment_started.on(self.on_dilc_experiment_started,
                                                                        spawn_new_threads=True)

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

        # Red agent for estimated position (from robot estimation)
        self.robot_map_agent_estimated = Agent(
            id=f"robot_map_agent_estimated", x=0, y=0, psi=0,
            size=0.1, arrow_length=0.25, arrow_width=0.05,
            color=[0.8, 0.2, 0.2],  # Red
            show_name=False
        )
        self.map_widget.map.addObject(self.robot_map_agent_estimated)

        # Green agent for tracked position (from OptiTrack) - hidden until first sample
        self.robot_map_agent_tracked = Agent(
            id=f"robot_map_agent_tracked", x=0, y=0, psi=0,
            size=0.1, arrow_length=0.25, arrow_width=0.05,
            color=[0.2, 0.8, 0.2],  # Green
            show_name=False,
            visible=False
        )
        self._tracker_agent_shown = False
        self._first_stream_tick: int | None = None
        self.map_widget.map.addObject(self.robot_map_agent_tracked)

        def map_double_click(data, *args, **kwargs):
            x = data['x']
            y = data['y']
            safety_margin = 0.2
            if testbed_size['x'][0] < x < testbed_size['x'][1] and testbed_size['y'][0] < y < testbed_size['y'][1]:
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

        def _on_position_mode_changed(*args, **kwargs):
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
            robot_x = self.robot_map_agent_estimated.data.get('x', 0)
            robot_y = self.robot_map_agent_estimated.data.get('y', 0)

            # Calculate endpoint of heading indicator line
            import math
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
            from robots.bilbo.testbed.objects import BoxObstacle
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
            from robots.bilbo.testbed.objects import BoxObstacle
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
            if not path_data or path_data.path_point_count == 0:
                return
            _draw_planned_path(path_data)

        self.robot.position_control.events.path_planned.on(_on_path_planned)

        # Also draw path when loaded (has compressed points now)
        def _on_path_loaded_viz(path_data: PathData, *args, **kwargs):
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

        psi_zero_button = Button(widget_id='psi_zero_button', text='Ψ=0', color=[0.4, 0.4, 0.4])
        psi_zero_button.callbacks.click.register(lambda *args, **kwargs: self.robot.position_control.turn_to(0))
        navigation_group.addWidget(psi_zero_button, row=1, column=1, width=2, height=2)

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

        # Update red (estimated) map agent from robot estimation state
        tick = self.robot.core.tick
        if self._first_stream_tick is None:
            self._first_stream_tick = tick
        if (tick - self._first_stream_tick) % 5 == 0:
            self.robot_map_agent_estimated.update(
                x=sample.estimation.state.x,
                y=sample.estimation.state.y,
                psi=sample.estimation.state.psi
            )

    # ------------------------------------------------------------------------------------------------------------------
    def on_new_tracker_sample(self, sample, *args, **kwargs):
        if not self._built:
            return
        if self.manager.tracker is not None and self.robot.id in self.manager.tracker.robots:
            state = self.manager.tracker.robots[self.robot.id].state

            # Show green (tracked) agent on first tracker sample
            if not self._tracker_agent_shown:
                self.robot_map_agent_tracked.updateConfig(visible=True)
                self._tracker_agent_shown = True

            # Update green (tracked) agent from OptiTrack
            self.robot_map_agent_tracked.update(x=state.x, y=state.y, psi=state.psi)

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
    def on_dilc_experiment_started(self, *args, **kwargs):
        ...

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

        try:
            self.app.removeFolder(self.folder)
        except Exception:
            pass

        for plot in self.plots:
            # plot.
            ...
        self.map_widget.onDelete()


# ======================================================================================================================
class BILBO_Application_App_Robot_Folder:
    folder: Folder

    # === INIT =========================================================================================================
    def __init__(self, robot: BILBO, app: App):
        self.robot = robot
        self.app = app
        self.folder = Folder(folder_id=robot.core.id)

        self._buildFolder()

    # === METHODS ======================================================================================================
    def _buildFolder(self):
        # --- MODE BUTTON (same behavior as in GUI Category) ---
        self.mode_button = MultiStateButton(
            id='mode_button',
            states=['OFF', 'BALANCING', 'POSITION'],
            color=[[0.4, 0, 0], [0, 0.4, 0], [0, 0, 0.4]],
            title='Mode',
        )
        self.folder.addObject(self.mode_button, row=1, column=2, width=1, height=1)

        # Map robot control mode <-> button label
        _mode_mapping = {
            BILBO_Control_Mode.OFF: 'OFF',
            BILBO_Control_Mode.BALANCING: 'BALANCING',
            BILBO_Control_Mode.VELOCITY: 'VELOCITY',
            BILBO_Control_Mode.POSITION: 'POSITION',
        }

        # Initialize button state from current robot mode
        try:
            self.mode_button.state = _mode_mapping[self.robot.control.mode]
        except Exception:
            # Fallback if anything unexpected happens
            self.mode_button.state = 'OFF'

        # Click handler: set robot control mode based on desired state
        def _mode_click_handler(*cb_args, **cb_kwargs):
            # Be defensive about callback signature: could be (state, index, ...) or (index, ...)
            idx = cb_kwargs.get('index', None)
            if idx is None:
                if len(cb_args) >= 2:
                    idx = cb_args[1]
                elif len(cb_args) >= 1:
                    idx = cb_args[0]
                else:
                    # Fallback to current state index if not provided
                    try:
                        idx = self.mode_button.states.index(self.mode_button.state)
                    except Exception:
                        idx = 0
            idx = int(idx)
            desired = self.mode_button.getStateByIndex(idx + 1)  # API is 1-based
            self.robot.control.setControlMode(
                BILBO_Control_Mode.OFF if desired == 'OFF' else BILBO_Control_Mode.BALANCING
            )

        self.mode_button.callbacks.click.register(_mode_click_handler)

        # --- TIC BUTTON (same behavior as in GUI Category) ---
        self.tic_button = MultiStateButton(
            id='tic_button',
            states=['OFF', 'ON'],
            color=[[0.4, 0, 0], [0, 0.4, 0]],
            title='TIC',
        )
        self.folder.addObject(self.tic_button, row=1, column=3, width=1, height=1)

        # Click handler: toggle TIC on the controller
        def _tic_click_handler(*cb_args, **cb_kwargs):
            idx = cb_kwargs.get('index', None)
            if idx is None:
                if len(cb_args) >= 2:
                    idx = cb_args[1]
                elif len(cb_args) >= 1:
                    idx = cb_args[0]
                else:
                    try:
                        idx = self.tic_button.states.index(self.tic_button.state)
                    except Exception:
                        idx = 0
            idx = int(idx)
            desired = self.tic_button.getStateByIndex(idx + 1)
            self.robot.control.enableTIC(desired == 'ON')

        self.tic_button.callbacks.click.register(_tic_click_handler)

        def robot_control_config_change_callback(config):
            tic_enabled = config['balancing_control']['tic']['enabled']
            self.tic_button.state = 'ON' if tic_enabled else 'OFF'

        self.robot.control.callbacks.configuration_changed.register(robot_control_config_change_callback)

        _mode_mapping = {
            BILBO_Control_Mode.OFF: 'OFF',
            BILBO_Control_Mode.BALANCING: 'BALANCING',
            BILBO_Control_Mode.VELOCITY: 'VELOCITY',
            BILBO_Control_Mode.POSITION: 'POSITION',
        }

        def robot_control_mode_change_callback(mode):
            self.mode_button.state = _mode_mapping[mode]

        self.robot.control.callbacks.mode_changed.register(robot_control_mode_change_callback)

        # --- Interface Buttons ---
        self.start_button = Button(widget_id='start_button', text='Start', color=[0.0, 0.4, 0.0])
        self.start_button.callbacks.click.register(self.robot.core.interface_events.start.set, discard_inputs=True)
        self.folder.addObject(self.start_button, row=2, column=1, width=1, height=1)

        self.resume_button = Button(widget_id='resume_button', text='Resume', color=[75 / 255, 82 / 255, 56 / 255])
        self.resume_button.callbacks.click.register(self.robot.core.interface_events.resume.set, discard_inputs=True)
        self.folder.addObject(self.resume_button, row=2, column=2, width=1, height=1)

        self.revert_button = Button(widget_id='revert_button', text='Revert', color=[59 / 255, 20 / 255, 120 / 255])
        self.revert_button.callbacks.click.register(self.robot.core.interface_events.revert.set, discard_inputs=True)
        self.folder.addObject(self.revert_button, row=2, column=3, width=1, height=1)

        self.stop_button = Button(widget_id='stop_button', text='Stop', color=[0.4, 0, 0])
        self.stop_button.callbacks.click.register(self.robot.core.interface_events.stop.set, discard_inputs=True)
        self.folder.addObject(self.stop_button, row=2, column=4, width=1, height=1)

        # --- Joystick Button ---
        self.joystick_button = Button(widget_id='joystick_button', image='gamepad.png')
        self.folder.addObject(self.joystick_button, row=2, column=6, width=1, height=1)

        # Check if joystick is assigned
        if js_control.robotIsAssigned(self.robot):
            self.joystick_button.dim(False)
        else:
            self.joystick_button.dim(True)

        def joystick_button_callback(*args, **kwargs):
            if js_control.robotIsAssigned(self.robot):
                return
            joystick = js_control.getFirstJoystick()
            if joystick is None:
                return
            js_control.assignJoystick(joystick, self.robot)

        def joystick_button_long_callback(*args, **kwargs):
            if js_control.robotIsAssigned(self.robot):
                js_control.unassignJoystick(self.robot.interfaces.joystick)

        self.joystick_button.callbacks.click.register(joystick_button_callback)
        self.joystick_button.callbacks.longClick.register(joystick_button_long_callback)

        def new_js_assignment_callback(joystick: Joystick, robot: BILBO):
            if robot == self.robot:
                self.joystick_button.dim(False)

        def js_assignment_removed_callback(joystick: Joystick, robot: BILBO):
            if robot == self.robot:
                self.joystick_button.dim(True)

        js_control.callbacks.new_assignment.register(new_js_assignment_callback)
        js_control.callbacks.assigment_removed.register(js_assignment_removed_callback)


# ======================================================================================================================
class BILBO_GUI_OverviewPage:
    page: Page
    manager: TestbedManager

    @dataclasses.dataclass
    class RobotContainer:
        robot: TestbedBILBO
        babylon: BabylonBilbo

    robots: dict[str, RobotContainer]
    _obstacle_babylon_objects: dict[str, Box]

    def __init__(self, manager: TestbedManager):
        self.manager = manager

        self.logger = Logger("Testbed Page")
        self.page = Page(id='testbed_page', name='Testbed')
        self.robots = {}
        self._obstacle_babylon_objects = {}
        self.babylon_visualization = None

        self._buildPage()

        self.manager.events.new_bilbo.on(self._on_new_testbed_robot)
        self.manager.events.bilbo_removed.on(self._on_testbed_robot_disconnected)
        self.manager.events.new_tracker_sample.on(self._on_new_tracker_sample)
        self.manager.events.initialized.on(self._on_testbed_initialized)
        self.manager.testbed.events.obstacle_added.on(self._on_obstacle_added)
        self.manager.testbed.events.obstacle_removed.on(self._on_obstacle_removed)

    # ------------------------------------------------------------------------------------------------------------------
    def _buildPage(self):
        # Statuses
        # Make a group
        # status_group = Widget_Group(group_id='status_group', title='Status', rows=1, columns=1, show_title=True)
        # self.page.addWidget(status_group, row=1, column=1, width=8, height=8)

        # Build tracker overview (disabled if OptiTrack not enabled)
        self._build_tracker_overview()

        # Build timecode group (disabled if timecode not enabled)
        self._build_timecode()

        self.babylon_widget = BabylonWidget(widget_id='babylon_widget')
        self.page.addWidget(self.babylon_widget, row=6, column=30, height=13, width=21)

        # Build extensions group (individual widgets disabled based on settings)
        self._build_display_group()

        # self.joystick_manager_widget = JoystickAssignmentWidget(
        #     joysticks= [
        #         {
        #             'id': 'joy1',
        #             'name': 'Joystick 1'
        #         },
        #         {
        #             'id': 'joy2',
        #             'name': 'Joystick 2'
        #         },
        #
        #     ],
        #     robots = [
        #         {
        #             'id': 'bilbo1',
        #             'name': 'BILBO 1'
        #         },
        #         {
        #             'id': 'bilbo2',
        #             'name': 'BILBO 2'
        #         },
        #         {
        #             'id': 'bilbo3',
        #             'name': 'BILBO 3'
        #         },
        #         {
        #             'id': 'bilbo4',
        #             'name': 'BILBO 4'
        #         },
        #         {
        #             'id': 'bilbo5',
        #             'name': 'BILBO 5'
        #         },
        #
        #     ]
        # )
        #
        # self.page.addWidget(self.joystick_manager_widget, row=5, width=14, height=14)

    # ------------------------------------------------------------------------------------------------------------------
    def _build_timecode(self):
        """Build the timecode group. Disabled if timecode is not enabled in settings."""
        timecode_enabled = self.manager.settings.extensions.timecode

        timecode_group = Widget_Group(group_id='timecode_group',
                                      title='Timecode',
                                      rows=1,
                                      columns=4,
                                      fill_empty=True,
                                      show_title=True)
        timecode_status_indicator = CircleIndicator()
        timecode_group.addWidget(timecode_status_indicator, row=1, column=1, width=1, height=1)
        timecode_fps = DigitalNumberWidget(increment=0.01, min_value=0, max_value=100, value=0,
                                           show_unused_digits=False)
        timecode_group.addWidget(timecode_fps, row=1, column=2, width=1, height=1)
        timecode_clock = DigitalClockWidget(display_format="hh:mm:ss")
        timecode_group.addWidget(timecode_clock, row=1, column=3, width=2, height=1)

        self.page.addWidget(timecode_group, row=13, column=1, width=10, height=2)

        # If timecode is not enabled, disable the group and skip callback registration
        if not timecode_enabled:
            timecode_group.disable()
            return

        def initialize_timecode(*args, **kwargs):
            fps = self.manager.timecode_server.get_fps()
            timecode_fps.value = fps
            timecode_status_indicator.updateConfig(color=[0, 0.8, 0])
            timecode_clock.set(self.manager.timecode_server.get_time())
            timecode_clock.start()

        def stop_timecode(*args, **kwargs):
            timecode_status_indicator.updateConfig(color=[0.8, 0, 0])
            timecode_clock.stop()
            timecode_clock.set(None)

        def update_timecode(timecode: Timecode):
            timecode_clock.set(timecode.to_seconds())
            timecode_status_indicator.blink(250)

        if self.manager.timecode_server.status == TimecodeServerStatus.running:
            initialize_timecode()
        else:
            stop_timecode()

        self.manager.timecode_server.events.initialized.on(initialize_timecode)
        self.manager.timecode_server.events.error.on(stop_timecode)
        self.manager.timecode_server.callbacks.zero_frame.register(update_timecode)

    # ------------------------------------------------------------------------------------------------------------------
    def _build_tracker_overview(self):
        """Build the tracker overview group. Disabled if OptiTrack is not enabled in settings."""
        optitrack_enabled = self.manager.settings.tracker.enabled

        tracker_group = Widget_Group(group_id='tracker_group',
                                     title='Tracker',
                                     rows=11,
                                     columns=3,
                                     show_title=True)
        self.page.addWidget(tracker_group, row=1, column=1, width=10, height=12)

        tracker_status = CircleIndicator()
        tracker_group.addWidget(tracker_status, row=1, column=1, width=1, height=1)

        rigid_body_text = TextWidget(text='Rigid Bodies')
        tracker_group.addWidget(rigid_body_text, row=2, column=1, width=3, height=1)

        # Table
        rb_table = Table(title='Rigid Bodies')
        rb_table.add_column(
            TextColumn(
                id='object_id',
                title='ID',
                width=0.7
            )
        )
        rb_table.add_column(
            IndicatorColumn(
                id='valid',
                title='Valid'
            )
        )

        tracker_group.addWidget(rb_table, row=3, column=1, width=3, height=4)

        tracked_objects_text = TextWidget(text='Tracked Objects')
        tracker_group.addWidget(tracked_objects_text, row=7, column=1, width=3, height=1)

        tracker_table = Table()
        tracker_table.add_column(
            TextColumn(
                id='object_id',
                title='ID',
                width=0.4
            )
        )
        tracker_table.add_column(
            NumberColumn(
                id='x',
                title='X',
                increment=0.01,
            )
        )
        tracker_table.add_column(
            NumberColumn(
                id='y',
                title='Y',
                increment=0.01,
            )
        )
        tracker_table.add_column(
            IndicatorColumn(
                id='valid',
                title='Valid'
            )
        )

        tracker_group.addWidget(tracker_table, row=8, column=1, width=3, height=4)

        # If OptiTrack is not enabled, disable the group and skip callback registration
        if not optitrack_enabled:
            tracker_group.disable()
            return

        def initialize_tracker(*args, **kwargs):
            tracker_status.updateConfig(color=[0, 0.8, 0])

            for obj_id, rigid_body in self.manager.tracker.rigid_bodies.items():
                rb_table.make_row(id=obj_id, object_id=obj_id, valid=[0.8, 0, 0])

        def tracker_error(*args, **kwargs):
            tracker_status.updateConfig(color=[0.8, 0, 0])

        def on_new_tracked_object(tracked_object):
            tracker_table.make_row(id=tracked_object.id,
                                   object_id=tracked_object.id,
                                   x=tracked_object.state.x,
                                   y=tracked_object.state.y,
                                   valid=[0.8, 0, 0])

        def on_tracked_object_removed(obj_id: str):
            row = tracker_table.get_row_by_id(row_id=obj_id)
            if row:
                tracker_table.delete_row(row)

        def tracker_new_sample(*args, **kwargs):
            if self.manager.tracker.samples % 5 == 0:
                tracker_status.blink(250)
            else:
                return
            # Go through the rigid bodies
            for rb_id, rigid_body_sample in self.manager.tracker.sample.items():
                row = rb_table.get_row_by_id(row_id=rb_id)
                if row:
                    cell = row.get_cell('valid')
                    if rigid_body_sample.valid:
                        cell.color = [0, 0.8, 0]
                    else:
                        cell.color = [0.8, 0, 0]

            # Go through the BILBOs
            for bilbo_id, bilbo in self.manager.tracker.robots.items():
                row = tracker_table.get_row_by_id(row_id=bilbo_id)
                if row:
                    cell_x = row.get_cell('x')
                    cell_y = row.get_cell('y')
                    cell_valid = row.get_cell('valid')
                    cell_x.set(bilbo.state.x)
                    cell_y.set(bilbo.state.y)

                    if bilbo.tracking_valid:
                        cell_valid.color = [0, 0.8, 0]
                    else:
                        cell_valid.color = [0.8, 0, 0]

            if self.manager.tracker.origin:
                row = tracker_table.get_row_by_id(row_id=self.manager.tracker.origin.id)
                if row:
                    cell_x = row.get_cell('x')
                    cell_y = row.get_cell('y')
                    cell_valid = row.get_cell('valid')
                    cell_x.set(self.manager.tracker.origin.state.x)
                    cell_y.set(self.manager.tracker.origin.state.y)
                    if self.manager.tracker.origin.tracking_valid:
                        cell_valid.color = [0, 0.8, 0]
                    else:
                        cell_valid.color = [0.8, 0, 0]

            if self.manager.tracker.limbo_bar:
                row = tracker_table.get_row_by_id(row_id=self.manager.tracker.limbo_bar.id)
                if row:
                    cell_x = row.get_cell('x')
                    cell_y = row.get_cell('y')
                    cell_valid = row.get_cell('valid')
                    cell_x.set(self.manager.tracker.limbo_bar.state.x)
                    cell_y.set(self.manager.tracker.limbo_bar.state.y)
                    if self.manager.tracker.limbo_bar.tracking_valid:
                        cell_valid.color = [0, 0.8, 0]
                    else:
                        cell_valid.color = [0.8, 0, 0]

        self.manager.tracker.events.initialized.on(initialize_tracker)
        self.manager.tracker.events.error.on(tracker_error)
        self.manager.tracker.events.new_sample.on(tracker_new_sample, max_rate=10)
        self.manager.tracker.events.new_tracked_object.on(on_new_tracked_object)
        self.manager.tracker.events.tracked_object_removed.on(on_tracked_object_removed)

    # ------------------------------------------------------------------------------------------------------------------
    def _build_display_group(self):
        """Build the display/extensions group with display text input and limbo bar slider.

        Widgets are disabled if their corresponding feature is not enabled in settings.
        """
        use_display = self.manager.settings.extensions.display
        use_limbobar = self.manager.settings.extensions.limbobar

        display_group = Widget_Group(
            group_id='display_group',
            title='Extensions',
            rows=2,
            columns=2,
            show_title=True
        )
        self.page.addWidget(display_group, row=1, width=10, height=4)

        # === Display Text Input ===
        self.display_text_input = InputWidget(
            widget_id='display_text_input',
            value='',
            datatype=None,
            title='Display',
            title_position='left',
            inputFieldAlign='center',
            inputFieldFontSize=12,
        )
        display_group.addWidget(self.display_text_input, row=1, column=1, width=2, height=1)

        if use_display:
            def on_display_text_changed(text: str):
                self.logger.info(f"Setting display text to: {text}")
                self.manager.extensions.display.set_text(text)

            self.display_text_input.callbacks.value_changed.register(on_display_text_changed)
        else:
            self.display_text_input.disable()

        # === Limbo Height Slider ===
        self.limbo_height_slider = ClassicSliderWidget(
            widget_id='limbo_height_slider',
            min_value=0,
            max_value=400,
            increment=5,
            value=0,
            title='Limbo Height',
            title_position='left',
            direction='horizontal',
            continuousUpdates=False,
            valuePosition='right',
        )
        display_group.addWidget(self.limbo_height_slider, row=2, column=1, width=2, height=1)

        if use_limbobar:
            def on_limbo_height_changed(height: float):
                height_m = height
                self.logger.info(f"Setting limbo bar height to: {height} mm")
                self.manager.extensions.limbo_bar.setHeight(height_m)

            self.manager.extensions.limbo_bar.setHeight(0)
            self.limbo_height_slider.callbacks.value_changed.register(on_limbo_height_changed)
        else:
            self.limbo_height_slider.disable()

    # ------------------------------------------------------------------------------------------------------------------
    def _on_new_testbed_robot(self, robot: TestbedBILBO, *args, **kwargs):
        if robot.id in self.robots:
            self.logger.warning(f'Testbed robot {robot.id} already exists. Skipping.')
            return

        color = robot.config.general.color if robot.config else [0.5, 0.5, 0.5]
        text = robot.config.general.short_id if robot.config else robot.id

        container = self.RobotContainer(
            robot=robot,
            babylon=BabylonBilbo(object_id=robot.id, color=color, text=text)
        )

        self.robots[robot.id] = container
        self.babylon_visualization.addObject(container.babylon)

        # Subscribe to the robot's own stream so the 3D model updates
        # from estimation state (works even without OptiTrack tracker)
        if isinstance(robot, RealTestbedBILBO):
            babylon_ref = container.babylon
            robot.robot.core.events.stream.on(
                lambda sample, _b=babylon_ref: _b.set_state(
                    x=sample.estimation.state.x,
                    y=sample.estimation.state.y,
                    theta=sample.estimation.state.theta,
                    psi=sample.estimation.state.psi,
                ),
                max_rate=20,
            )

        # ------------------------------------------------------------------------------------------------------------------

    def _on_testbed_robot_disconnected(self, robot_id: str, *args, **kwargs):
        if robot_id not in self.robots:
            self.logger.warning(f'Testbed robot {robot_id} not found. Skipping.')
            return

        self.babylon_visualization.removeObject(self.robots[robot_id].babylon)
        del self.robots[robot_id]

        # ------------------------------------------------------------------------------------------------------------------

    def _on_new_tracker_sample(self, *args, **kwargs):
        for robot in self.robots.values():
            state = robot.robot.state
            robot.babylon.set_state(
                x=state.x,
                y=state.y,
                theta=state.theta,
                psi=state.psi,
            )

        # Update obstacle 3D positions
        for obs_id, box in self._obstacle_babylon_objects.items():
            if obs_id in self.manager.testbed.obstacles:
                obs = self.manager.testbed.obstacles[obs_id]
                s = obs.state
                box.setPosition(x=s.x, y=s.y, z=0.125)
                import qmt
                box.setOrientation(qmt.quatFromAngleAxis(s.psi, [0, 0, 1]))

    # ------------------------------------------------------------------------------------------------------------------
    def _on_obstacle_added(self, obstacle, *args, **kwargs):
        """Add a box obstacle to the Babylon 3D view."""
        from robots.bilbo.testbed.objects import BoxObstacle
        if not isinstance(obstacle, BoxObstacle):
            return
        if self.babylon_visualization is None:
            return
        obs_id = obstacle.id
        if obs_id in self._obstacle_babylon_objects:
            return

        s = obstacle.state
        box = Box(
            object_id=f"obstacle_{obs_id}",
            color=[0.8, 0.15, 0.15],
            alpha=0.8,
            size={'x': obstacle.config.width, 'y': obstacle.config.height, 'z': 0.25},
        )
        box.setPosition(x=s.x, y=s.y, z=0.125)
        import qmt
        box.setOrientation(qmt.quatFromAngleAxis(s.psi, [0, 0, 1]))
        self.babylon_visualization.addObject(box)
        self._obstacle_babylon_objects[obs_id] = box

    # ------------------------------------------------------------------------------------------------------------------
    def _on_obstacle_removed(self, obstacle, *args, **kwargs):
        """Remove a box obstacle from the Babylon 3D view."""
        from robots.bilbo.testbed.objects import BoxObstacle
        if isinstance(obstacle, BoxObstacle):
            obs_id = obstacle.id
        elif isinstance(obstacle, str):
            obs_id = obstacle
        else:
            return
        if obs_id in self._obstacle_babylon_objects:
            box = self._obstacle_babylon_objects.pop(obs_id)
            if self.babylon_visualization is not None:
                self.babylon_visualization.removeObject(box)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_testbed_initialized(self, *args, **kwargs):
        # Babylon
        testbed_size = self.manager.settings.testbed.size

        target_x = (testbed_size['x'][0] + testbed_size['x'][1]) / 2
        target_y = (testbed_size['y'][0] + testbed_size['y'][1]) / 2

        self.babylon_visualization = BabylonVisualization(
            id='babylon', babylon_config=
            {
                'title': 'BILBO Testbed',
                'camera': {
                    'target': [target_x, target_y, 0],
                    'position': [1.5, -0.9, 1.334]
                }
            }
        )

        self.babylon_widget.set_babylon(self.babylon_visualization)
        self.babylon_visualization.start()

        floor = SimpleFloor('floor',
                            size_x=testbed_size['x'],
                            size_y=testbed_size['y'])
        self.babylon_visualization.addObject(floor)

        # Add existing testbed obstacles to Babylon
        for obstacle in self.manager.testbed.obstacles.values():
            self._on_obstacle_added(obstacle)

        # testbed_size = [3, 3]  # Size in meters

        # # Floor is kept larger than testbed for visual purposes
        # floor = SimpleFloor('floor', size_y=50, size_x=50, texture='floor_bright.png')
        # self.babylon_visualization.addObject(floor)
        #
        # # Wall length matches testbed size
        # # Wall positions are offset by half the testbed size to create the boundary
        # wall1 = WallFancy('wall1', length=testbed_size[0], texture='wood4.png', include_end_caps=True)
        # wall1.setPosition(y=testbed_size[1] / 2)
        # self.babylon_visualization.addObject(wall1)
        #
        # wall2 = WallFancy('wall2', length=testbed_size[0], texture='wood4.png', include_end_caps=True)
        # self.babylon_visualization.addObject(wall2)
        # wall2.setPosition(y=-testbed_size[1] / 2)
        #
        # wall3 = WallFancy('wall3', length=testbed_size[1], texture='wood4.png')
        # wall3.setPosition(x=testbed_size[0] / 2)
        # wall3.setAngle(np.pi / 2)
        # self.babylon_visualization.addObject(wall3)
        #
        # wall4 = WallFancy('wall4', length=testbed_size[1], texture='wood4.png')
        # wall4.setPosition(x=-testbed_size[0] / 2)
        # wall4.setAngle(np.pi / 2)
        # self.babylon_visualization.addObject(wall4)


# ======================================================================================================================
@callback_definition
class BILBO_Application_GUI_Callbacks:
    emergency_stop: CallbackContainer


class BILBO_Application_GUI:
    gui: GUI
    app: App
    categories: dict
    robot_ui: dict[str, RobotUI]
    # robot_categories: dict[str, BILBO_Application_GUI_Robot_Category]
    robot_app_folders: dict[str, BILBO_Application_App_Robot_Folder]
    mdns_advertiser: MDNSAdvertiser | None
    port_forwarder: PortForwarder | None

    # === INIT =========================================================================================================
    def __init__(self,
                 settings,
                 host,
                 testbed_manager: TestbedManager,
                 cli: CLI = None,
                 joystick_control: BILBO_JoystickControl | None = None,
                 enable_mdns: bool = True,
                 mdns_hostname: str = MDNS_HOSTNAME,
                 mdns_use_port_80: bool = False):

        self.application_settings = settings
        self.callbacks = BILBO_Application_GUI_Callbacks()
        self.host = host
        self.enable_mdns = enable_mdns
        self.mdns_hostname = mdns_hostname
        self.mdns_use_port_80 = mdns_use_port_80

        self.gui = GUI(
            id='bilbo_application',
            host=host,
            run_js=True
        )

        self.app = App(
            app_id='bilbo_application_app',
            host=host,
            run_js_app=False,
        )

        self.testbed_manager = testbed_manager
        self.gui.cli_terminal.setCLI(cli)
        self.joystick_control = joystick_control

        global js_control
        js_control = joystick_control

        # GUI Callbacks
        self.gui.callbacks.emergency_stop.register(self.callbacks.emergency_stop.call)

        self.categories = {}
        self.robot_ui = {}

        self._addCategoriesAndPages()

        self._addApplications()

        self.logger = Logger('gui')

        # Reroute all logs to the CLI
        addLogRedirection(self._logRedirection, minimum_level='INFO')

        # mDNS advertiser for network discovery
        self.mdns_advertiser = None
        # Port forwarder for port 80 access (optional, requires sudo)
        self.port_forwarder = None

        # Subscribe to testbed manager events for robot connect/disconnect
        self.testbed_manager.events.new_bilbo.on(self._on_new_bilbo)
        self.testbed_manager.events.bilbo_removed.on(self._on_bilbo_removed)

    # === METHODS ======================================================================================================
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.gui.start()
        self.app.start()

        # Start mDNS advertisement so the GUI is discoverable on the network
        if self.enable_mdns:
            self._start_mdns()

    # ------------------------------------------------------------------------------------------------------------------
    def _start_mdns(self):
        """Start mDNS advertisement to make the GUI discoverable on the network.

        If mdns_use_port_80 is True, also starts a port forwarder on port 80 to allow
        access without specifying a port (requires running with sudo).
        """
        # Determine which port to advertise
        advertised_port = PORT_JS_APP

        if self.mdns_use_port_80:
            # Start port forwarder: port 80 -> GUI port
            self.port_forwarder = PortForwarder(listen_port=80, target_port=PORT_JS_APP, target_host=self.host)
            if self.port_forwarder.start():
                advertised_port = 80
            else:
                self.logger.error("Cannot bind to port 80 - requires sudo. Falling back to port 8400.")
                self.port_forwarder = None

        # Start mDNS advertisement
        self.mdns_advertiser = MDNSAdvertiser(
            hostname=self.mdns_hostname,
            port=advertised_port
        )
        if self.mdns_advertiser.start():
            if advertised_port == 80:
                self.logger.info(f"GUI advertised on network: http://{self.mdns_hostname}.local/gui")
            else:
                self.logger.info(f"GUI advertised on network: http://{self.mdns_hostname}.local:{advertised_port}/gui")
        else:
            self.logger.warning("mDNS advertisement failed. GUI will only be accessible via direct IP:port.")

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        """Clean up resources including mDNS advertisement and port forwarder."""
        if self.mdns_advertiser:
            self.mdns_advertiser.stop()
        if self.port_forwarder:
            self.port_forwarder.stop()

    # ------------------------------------------------------------------------------------------------------------------
    def addRobot(self, robot: BILBO):
        self.robot_ui[robot.id] = RobotUI(robot=robot,
                                          manager=self.testbed_manager,
                                          gui=self.gui,
                                          app=self.app,
                                          application_settings=self.application_settings)

        self.gui.callout_handler.add(callout_type=CalloutType.INFO,
                                     title='Robot Connected',
                                     content=f'Robot {robot.id} connected.',
                                     timeout=5)

    # ------------------------------------------------------------------------------------------------------------------
    def removeRobot(self, robot_id: str):
        if robot_id not in self.robot_ui:
            return
        self.logger.important(f'Removing robot {robot_id} from GUI')

        self.gui.callout_handler.add(callout_type=CalloutType.WARNING,
                                     title='Robot Disconnected',
                                     content=f'Robot {robot_id} disconnected.',
                                     timeout=5)
        self.robot_ui[robot_id].close()
        del self.robot_ui[robot_id]

    # ------------------------------------------------------------------------------------------------------------------
    def _on_new_bilbo(self, testbed_bilbo: TestbedBILBO, *args, **kwargs):
        """Handle new robot from testbed manager. Wait for initialization before building UI."""
        if not isinstance(testbed_bilbo, RealTestbedBILBO):
            return

        robot = testbed_bilbo.robot

        # Set GUI reference on experiment handler for file picker functionality
        robot.experiment_handler.set_gui(self.gui)

        # Wait for first sample before building robot UI
        if not robot.core.initialized:
            robot.core.events.initialized.on(
                callback=Callback(
                    function=self.addRobot,
                    inputs={'robot': robot},
                    discard_inputs=True
                ),
                once=True,
                discard_data=True
            )
        else:
            self.addRobot(robot)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_bilbo_removed(self, robot_id: str, *args, **kwargs):
        """Handle robot disconnect from testbed manager."""
        self.removeRobot(robot_id)

    # === PRIVATE METHODS ==============================================================================================
    def _addCategoriesAndPages(self):
        # Application category
        category_application = Category(id='application', name='Application', icon='🎛️')
        self.gui.addCategory(category_application)
        self.categories['application'] = {'category': category_application}

        # Pages
        # page_overview = Page(id='overview', name='Overview')
        # category_application.addPage(page_overview)
        #
        # page_robots = Page(id='robots', name='Robots')
        # category_application.addPage(page_robots)

        self.testbed_page = BILBO_GUI_OverviewPage(self.testbed_manager)
        category_application.addPage(self.testbed_page.page)

        self.categories['application']['pages'] = {
            'testbed': self.testbed_page.page,
        }

        # Robots Category
        category_robots = Category(id='robots', name='Robots', icon='🤖', number_of_pages=1, max_pages=1)
        self.gui.addCategory(category_robots)
        self.categories['robots'] = {'category': category_robots}

        robots_overview = Page(id='overview', name='Overview')
        category_robots.addPage(robots_overview)
        self.categories['robots']['pages'] = {'overview': robots_overview}

    # # ------------------------------------------------------------------------------------------------------------------
    # def _addRobotCategory(self, robot_id, robot: BILBO):
    #     self.robot_categories[robot_id] = BILBO_Application_GUI_Robot_Category(robot, self.gui)
    #     self.categories['robots']['category'].addCategory(self.robot_categories[robot_id].category)

    # ------------------------------------------------------------------------------------------------------------------
    def _removeRobotCategory(self, robot_id):
        if robot_id in self.robot_categories:
            self.categories['robots']['category'].removeCategory(self.robot_categories[robot_id].category)
            del self.robot_categories[robot_id]

    # # ------------------------------------------------------------------------------------------------------------------
    # def _addRobotFolder_App(self, robot_id, robot: BILBO):
    #     self.robot_app_folders[robot_id] = BILBO_Application_App_Robot_Folder(robot, self.app)
    #     self.app.addFolder(self.robot_app_folders[robot_id].folder)

    # ------------------------------------------------------------------------------------------------------------------
    def _removeRobotFolder_App(self, robot_id):
        if robot_id in self.robot_app_folders:
            self.app.removeFolder(self.robot_app_folders[robot_id].folder)
            del self.robot_app_folders[robot_id]

    # ------------------------------------------------------------------------------------------------------------------
    def _addApplications(self):
        # BILBO Applications
        # 1. Input viewer
        input_viewer_button = Button(widget_id='input_viewer_button', text='Input Viewer')
        # self.gui.addApplicationButton(input_viewer_button)
        # input_viewer_button.callbacks.click.register(self._openInputViewer)

    # ------------------------------------------------------------------------------------------------------------------
    def _testPopupOpen(self, sender, *args, **kwargs):

        popup = YesNoPopup()
        self.gui.openPopup(popup, client=sender)

    # ------------------------------------------------------------------------------------------------------------------
    def _openInputViewer(self, sender, *args, **kwargs):

        input_viewer_app = InputViewerApplication()
        input_viewer_app.open(self.gui, sender)

    # ------------------------------------------------------------------------------------------------------------------
    def _logRedirection(self, log_entry, log, logger, level):
        print_text = f"[{logger.name}] {log}"
        color = LOGGING_COLORS[level]
        color = [c / 255 for c in color]
        self.gui.print(print_text, color=color)
        self.app.print(print_text, color=color)
