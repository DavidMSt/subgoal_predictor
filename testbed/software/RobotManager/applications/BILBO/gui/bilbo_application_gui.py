import dataclasses
import time
from random import randint, random, uniform
from typing import Dict, Optional, Callable

import numpy as np
from qmt import wrapToPi

from applications.BILBO.gui.applications.dilc_app import DILC_APP
# === CUSTOM MODULES ===================================================================================================
from applications.BILBO.gui.applications.input_viewer import InputViewerApplication
from applications.BILBO.testbed.testbed_manager import BILBO_TestbedManager, BILBO_TestbedAgent
from core.utils.callbacks import callback_definition, CallbackContainer, Callback
from core.utils.colors import get_color_from_palette, random_color_from_palette, get_palette
from core.utils.lipo import lipo_soc
from core.utils.logging_utils import Logger, addLogRedirection, LOGGING_COLORS
from core.utils.time import setTimeout, set_timeout, setInterval
from core.utils.timecode.timecode import Timecode
from core.utils.timecode.timecode_server import TimecodeServerStatus
from extensions.babylon.src.babylon import BabylonVisualization
from extensions.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo
from extensions.babylon.src.lib.objects.box.box import WallFancy
from extensions.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.cli.cli import CLI
from extensions.gui.src.app import App, Folder
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.map.map import MapWidget
from extensions.gui.src.lib.map.map_objects import Agent
from extensions.gui.src.lib.objects.objects import Widget_Group, ContextMenuItem, ContextMenuGroup
from extensions.gui.src.lib.objects.python.babylon_widget import BabylonWidget
from extensions.gui.src.lib.objects.python.buttons import MultiStateButton, Button
from extensions.gui.src.lib.objects.python.callout import CalloutType, CalloutButton
from extensions.gui.src.lib.objects.python.indicators import BatteryIndicatorWidget, ConnectionIndicator, \
    InternetIndicator, JoystickIndicator, ProgressIndicator, CircleIndicator
from extensions.gui.src.lib.objects.python.number import DigitalNumberWidget, DigitalClockWidget
from extensions.gui.src.lib.objects.python.popup import YesNoPopup, Popup
from extensions.gui.src.lib.objects.python.table import Table, TextColumn, IndicatorColumn, NumberColumn, TableGroup, CheckboxColumn
from extensions.gui.src.lib.objects.python.dial import RotaryDialWidget
from extensions.gui.src.lib.objects.python.checkbox import CheckboxWidget
from extensions.gui.src.lib.objects.python.text_input import InputWidget
from extensions.gui.src.lib.objects.python.sliders import ClassicSliderWidget
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

# from robots.bilbo.robot.experiment.experiments import DILC_Experiment

# === GLOBAL VARIABLES =================================================================================================
js_control: Optional[BILBO_JoystickControl] = None


# # ======================================================================================================================
# class BILBO_Application_GUI_Robot_Category:
#     robot: BILBO
#     category: Category
#     pages: Dict[str, Page]
#     gui: GUI
#
#     # === INIT =========================================================================================================
#     def __init__(self, robot: BILBO, gui: GUI):
#         self.robot = robot
#         self.gui = gui
#
#         self.pages: Dict[str, Page] = {}
#         self.category = Category(id=robot.id, icon='🤖')
#         self._buildPages()
#
#         self.robot.core.events.stream.on(self._streamCallback)
#         self.logger = Logger(f"Category {self.robot.id}")
#
#         # Register some events
#         self.robot.experiment_handler.events.dilc_experiment_started.on(self._onDILCExperimentStarted,
#                                                                         spawn_new_threads=True)
#
#     # === METHODS ======================================================================================================
#
#     # === PRIVATE HELPERS ==============================================================================================
#     @staticmethod
#     def _palette(i: int) -> list[float]:
#         """Convenience access to a consistent pastel palette."""
#         return get_color_from_palette('pastel', 5, i)
#
#     @staticmethod
#     def _classify_connection_strength(signal_strength: float) -> str:
#         """Map a numeric signal strength (0..100) to low/medium/high."""
#         if signal_strength > 85:
#             return 'high'
#         if signal_strength > 30:
#             return 'medium'
#         return 'low'
#
#     @staticmethod
#     def _create_toggle_button(
#             parent_group: Widget_Group,
#             *,
#             widget_id: str,
#             title: str,
#             grid_row: int,
#             grid_column: int,
#             states: tuple = ('OFF', 'ON'),
#             colors: tuple = ([0.4, 0, 0], [0, 0.4, 0]),
#             on_click: Optional[Callable[[str], None]] = None,
#             **kwargs
#     ) -> MultiStateButton:
#         """
#         Create a 2-state toggle button and (optionally) wire a simple on_click handler
#         that gets the chosen state ('OFF'|'ON' or custom states).
#
#         NOTE: The click callback from MultiStateButton may pass (state, index, ...)
#         OR just (index, ...). This handler handles both.
#         """
#         btn = MultiStateButton(
#             id=widget_id,
#             states=list(states),
#             color=colors,
#             title=title,
#             **kwargs,
#         )
#         parent_group.addWidget(btn, row=grid_row, column=grid_column, width=2, height=2)
#
#         if on_click is not None:
#             def _handler(*cb_args, **cb_kwargs):
#                 # Try to find the index argument in a resilient way
#                 idx = cb_kwargs.get('index', None)
#                 if idx is None:
#                     if len(cb_args) >= 2:
#                         # (state, index, ...)
#                         idx = cb_args[1]
#                     elif len(cb_args) >= 1:
#                         # (index, ...)
#                         idx = cb_args[0]
#                     else:
#                         # Fallback: use current state position (best-effort)
#                         try:
#                             idx = btn.states.index(btn.state)
#                         except Exception:
#                             idx = 0
#                 # Convert to int in case we got a string/np scalar
#                 idx = int(idx)
#                 desired_state = btn.getStateByIndex(idx + 1)  # API is 1-based
#                 on_click(desired_state)
#
#             btn.callbacks.click.register(_handler)
#
#         return btn
#
#     def _add_plot(
#             self,
#             page: Page,
#             *,
#             widget_id: str,
#             title: str,
#             color_index: int,
#             timeseries_id: str,
#             series_name: str,
#             unit: str,
#             vmin: float,
#             vmax: float,
#             grid_column: int,
#             grid_width: int = 9,
#             grid_height: int = 9,
#     ):
#         """Create a plot widget with a dedicated Y-axis + a single timeseries, add to page, and return both."""
#         # New widget class + API: Y-axis is separate from the timeseries
#         plot = RT_Plot_Widget(
#             widget_id=widget_id,
#             plot_config={
#                 "title": title,
#                 "show_title": True,
#                 "legend_label_type": "point",
#             },
#             server_mode=ServerMode.EXTERNAL,
#             update_mode=UpdateMode.CONTINUOUS,
#         )
#         page.addWidget(plot, column=grid_column, width=grid_width, height=grid_height)
#
#         # Palette helper -> ensure RGBA
#         base_col = list(self._palette(color_index))
#         if len(base_col) == 3:
#             rgba = base_col + [1.0]
#         else:
#             rgba = base_col[:4]
#
#         # Add a dedicated Y axis for this series
#         y_axis_id = f"{timeseries_id}_y"
#         y_axis = plot.plot.add_y_axis(
#             y_axis_id,
#             {
#                 "label": f"{series_name} [{unit}]" if unit else series_name,
#                 "min": vmin,
#                 "max": vmax,
#                 "color": rgba,
#                 "grid_color": [0.5, 0.5, 0.5, 0.4],
#                 "precision": 2,
#                 "highlight_zero": True,
#                 "side": "left",
#             },
#         )
#
#         # Add the timeseries bound to that Y axis
#         ts = TimeSeries(
#             id=timeseries_id,
#             y_axis=y_axis,  # can pass the object or its id
#             name=series_name,
#             unit=unit,
#             color=rgba,
#             fill_color=rgba[:-1] + [0.15] if len(rgba) == 4 else base_col + [0.15],
#             fill=False,
#             tension=0.0,
#             precision=2,
#             width=2,
#         )
#         ts.set_value(0.0)
#         plot.plot.add_timeseries(ts)
#
#         return plot, ts
#
#     @staticmethod
#     def _add_digital_number(
#             parent_group: Widget_Group,
#             *,
#             widget_id: str,
#             row: int,
#             title: str,
#             min_value: float,
#             max_value: float,
#             increment: float,
#             **kwargs
#     ) -> DigitalNumberWidget:
#         dn = DigitalNumberWidget(
#             widget_id=widget_id,
#             min_value=min_value,
#             max_value=max_value,
#             value=0,
#             increment=increment,
#             title=title,
#             title_position='left',
#             color=[0.3, 0.3, 0.3],
#             warn_on_out_of_bounds=False,
#             **kwargs,
#         )
#         parent_group.addWidget(dn, row=row, column=1, width=10, height=1)
#         return dn
#
#     # === PRIVATE METHODS ==============================================================================================
#     def _buildPages(self):
#         page_overview = Page(id='overview', name='Overview')
#         self.category.addPage(page_overview)
#         self.pages['overview'] = page_overview
#
#         self._buildOverviewPage()
#
#         page_control = Page(id='control', name='Control', icon='🎛️')
#         self.category.addPage(page_control)
#         self.pages['control'] = page_control
#
#         page_experiment = Page(id='experiment', name='Experiment', icon='🧪')
#         self.category.addPage(page_experiment)
#         self.pages['experiment'] = page_experiment
#
#         page_data = Page(id='data', name='Data', icon='📈')
#         self.category.addPage(page_data)
#         self.pages['data'] = page_data
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def _buildOverviewPage(self):
#         time.sleep(0.01)
#         overview_page = self.pages['overview']
#
#         # --- GENERAL GROUP ---
#         self.general_group = Widget_Group(group_id='general_group', title='General', rows=5, columns=11)
#         overview_page.addWidget(self.general_group, row=1, column=1, width=11, height=6)
#         self._createGeneralGroup()
#
#         # --- CONTROL GROUP ---
#         self.control_group = Widget_Group(group_id='control_group', title='Control', rows=11, columns=11,
#                                           show_title=True)
#         overview_page.addWidget(self.control_group, row=7, column=1, width=11, height=12)
#
#         # --- EXPERIMENT GROUP ---
#         self.experiment_group = Widget_Group(group_id='experiment_group', title='Experiment', rows=17, columns=11,
#                                              show_title=True)
#         overview_page.addWidget(self.experiment_group, row=1, column=12, width=11, height=18)
#         self._createExperimentGroup()
#
#         # --- DATA GROUP ---
#         self.data_group = Widget_Group(group_id='data_group', title='Data', rows=17, columns=10, show_title=True)
#         overview_page.addWidget(self.data_group, row=1, column=23, width=10, height=18)
#         self._createDataGroup()
#
#         # --- MODE BUTTON ---
#         mode_button = self._create_toggle_button(
#             self.control_group,
#             widget_id='mode_button',
#             title='Mode',
#             grid_row=5,
#             grid_column=1,
#             states=['OFF', 'BALANCING', 'VELOCITY'],
#             colors=[[0.4, 0, 0], [0, 0.4, 0], [0.4, 0.4, 0]],
#             on_click=lambda desired: self.robot.control.setControlMode(
#                 BILBO_Control_Mode.OFF if desired == 'OFF' else BILBO_Control_Mode.BALANCING
#             ),
#             tooltip='Enable/disable control mode',
#         )
#
#         mode_mapping = {
#             BILBO_Control_Mode.OFF: 'OFF',
#             BILBO_Control_Mode.BALANCING: 'BALANCING',
#             BILBO_Control_Mode.VELOCITY: 'VELOCITY',
#             BILBO_Control_Mode.POSITION: 'POSITION',
#         }
#
#         # Initial state
#         if self.robot.control.mode is not None:
#             mode_button.state = mode_mapping[self.robot.control.mode]
#
#         # Keep the button in sync with robot mode changes
#         def robot_control_mode_change_callback(mode):
#             mode_button.state = mode_mapping[mode]
#
#         self.robot.control.events.mode_changed.on(robot_control_mode_change_callback)
#
#         # --- TIC BUTTON ---
#         self.tic_button = self._create_toggle_button(
#             self.control_group,
#             widget_id='tic_button',
#             title='TIC',
#             grid_row=5,
#             grid_column=4,
#             on_click=lambda desired: self.robot.control.enableTIC(desired == 'ON'),
#             tooltip='Enable/disable Theta Integral Control',
#         )
#
#         # --- VIC BUTTON ---
#         # Note: In the original code, VIC button is display-only and driven by config changes.
#         # We keep that behavior (no click handler) to avoid altering semantics.
#         self.vic_button = self._create_toggle_button(
#             self.control_group,
#             widget_id='vic_button',
#             title='VIC',
#             grid_row=5,
#             grid_column=7,
#             on_click=None,
#             tooltip='Enable/disable Velocity Integral Control',
#         )
#
#         # Keep TIC/VIC buttons in sync with configuration changes
#         def robot_control_config_change_callback(config):
#             self.logger.important("Control config changed")
#             tic_enabled = config['balancing_control']['tic']['enabled']
#             self.tic_button.state = 'ON' if tic_enabled else 'OFF'
#
#             vic_enabled = config['balancing_control']['vic']['enabled']
#             self.vic_button.state = 'ON' if vic_enabled else 'OFF'
#
#         # self.robot.control.events.configuration_changed.on(robot_control_config_change_callback)
#
#         def on_tic_mode_change(mode):
#             self.tic_button.state = 'ON' if mode else 'OFF'
#
#         self.robot.control.events.tic_mode_changed.on(on_tic_mode_change)
#
#         # --- PLOTS ---
#         # Theta
#         self.theta_plot, self.theta_timeseries = self._add_plot(
#             overview_page,
#             widget_id='theta_plot',
#             title='Theta',
#             color_index=0,
#             timeseries_id='theta_ds',
#             series_name='Theta',
#             unit='deg',
#             vmin=-100,
#             vmax=100,
#             grid_column=33,
#         )
#
#         # Theta Dot
#         self.theta_dot_plot, self.theta_dot_timeseries = self._add_plot(
#             overview_page,
#             widget_id='theta_dot_plot',
#             title='Theta Dot',
#             color_index=1,
#             timeseries_id='theta_dot_ds',
#             series_name='Theta Dot',
#             unit='deg/s',
#             vmin=-800,
#             vmax=800,
#             grid_column=33,
#         )
#
#         # V
#         self.v_plot, self.v_timeseries = self._add_plot(
#             overview_page,
#             widget_id='v_plot',
#             title='V',
#             color_index=2,
#             timeseries_id='v_ds',
#             series_name='V',
#             unit='m/s',
#             vmin=-2,
#             vmax=2,
#             grid_column=42,
#         )
#
#         # Psi Dot
#         self.psi_dot_plot, self.psi_dot_timeseries = self._add_plot(
#             overview_page,
#             widget_id='psi_dot_plot',
#             title='Psi Dot',
#             color_index=3,
#             timeseries_id='psi_dot_ds',
#             series_name='Psi Dot',
#             unit='deg/s',
#             vmin=-360,
#             vmax=360,
#             grid_column=42,
#         )
#
#         # overview_page.addWidget(test_button)
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def _createGeneralGroup(self):
#
#         self.general_status_widget = StatusWidget(
#             widget_id='general_status_widget',
#             title='Status',
#             elements={
#                 'el1': StatusWidgetElement(label='Status',
#                                            color=[0, 0.5, 0],
#                                            status='ok',
#                                            ),
#                 'el2': StatusWidgetElement(label='Controller',
#                                            color=[0, 0.5, 0],
#                                            status='running',
#                                            ),
#                 'el3': StatusWidgetElement(label='Experiment',
#                                            color=[0.5, 0.5, 0.5],
#                                            status='idle',
#                                            )
#
#             }
#         )
#         self.general_group.addWidget(self.general_status_widget, row=1, column=1, width=11, height=3)
#
#         # Battery
#         self.battery_indicator = BatteryIndicatorWidget(
#             widget_id='battery_indicator',
#             label_position='center',
#             show='voltage',
#         )
#         self.general_group.addWidget(self.battery_indicator, row=4, column=9, width=3, height=2)
#
#         # Connection
#         self.connection_strength_indicator = ConnectionIndicator(widget_id='connection_strength_indicator')
#         self.general_group.addWidget(self.connection_strength_indicator, row=4, column=1, width=3, height=2)
#
#         # Internet
#         self.internet_indicator = InternetIndicator(widget_id='internet_indicator')
#         self.general_group.addWidget(self.internet_indicator, row=4, column=4, width=2, height=2)
#
#         # Joystick indicator + context menu
#         self.joystick_indicator = JoystickIndicator(widget_id='joystick_indicator')
#         self.joystick_indicator.setValue(False)
#         self.general_group.addWidget(self.joystick_indicator, row=4, column=6, width=3, height=2)
#
#         # Context menu group
#         joystick_group = ContextMenuGroup(id='joystick_group', name='Joysticks')
#         self.joystick_indicator.context_menu.addItem(joystick_group)
#
#         # Guard: if joystick control is not provided, stop here
#         if js_control is None:
#             return
#
#         self.joystick_contextmenu_items: Dict[str, dict] = {}
#
#         def _register_item(joystick):
#             joystick_id = str(joystick.id)
#             item = ContextMenuItem(id=joystick_id, name=f"{joystick.name} (ID: {joystick_id})")
#             joystick_group.addItem(item)
#
#             # Clicking assigns the joystick to this robot
#             item.callbacks.click.register(
#                 Callback(function=js_control.assignJoystick, inputs={'joystick': joystick, 'bilbo': self.robot})
#             )
#
#             self.joystick_contextmenu_items[joystick_id] = {
#                 'item': item,
#                 'joystick': joystick,
#                 'assignment': None,
#             }
#
#         # Initial population
#         for joystick_id, joystick_data in js_control.getJoysticksWithAssignments().items():
#             _register_item(joystick_data['joystick'])
#
#         # Live updates
#         def add_joystick_menu_item(joystick, *args, **kwargs):
#             _register_item(joystick)
#
#         def remove_joystick_menu_item(joystick, *args, **kwargs):
#             jid = str(joystick.id)
#             if jid in self.joystick_contextmenu_items:
#                 joystick_group.removeItem(self.joystick_contextmenu_items[jid]['item'])
#                 del self.joystick_contextmenu_items[jid]
#
#         def new_assignment(joystick, robot: BILBO, *args, **kwargs):
#             self.logger.info(f'New assignment: {joystick.id} -> {robot.id}')
#             jid = str(joystick.id)
#             if jid in self.joystick_contextmenu_items:
#                 item = self.joystick_contextmenu_items[jid]
#                 if robot == self.robot:
#                     item['item'].name = f"{item['joystick'].name} (ID: {jid}) ✅"
#                 else:
#                     item['item'].name = f"{item['joystick'].name} (ID: {jid}) (-> {robot.id})"
#
#         def assignment_removed(joystick, robot: BILBO, *args, **kwargs):
#             self.logger.info(f'Assignment removed: {joystick.id} -> {robot.id}')
#             jid = str(joystick.id)
#             if jid in self.joystick_contextmenu_items:
#                 item = self.joystick_contextmenu_items[jid]
#                 item['item'].name = f"{item['joystick'].name} (ID: {jid})"
#
#         js_control.callbacks.new_joystick.register(add_joystick_menu_item)
#         js_control.callbacks.joystick_disconnected.register(remove_joystick_menu_item)
#         js_control.callbacks.new_assignment.register(new_assignment)
#         js_control.callbacks.assigment_removed.register(assignment_removed)
#
#         # Click callback on the joystick indicator
#         def joystick_indicator_click_callback(*args, **kwargs):
#             # Check if our robot has a joystick assigned
#             if js_control is not None:
#                 joystick = js_control.robotIsAssigned(self.robot)
#                 if joystick is not None:
#                     # If so, open the context menu
#                     joystick.rumble(strength=1, duration=1000)
#
#         self.joystick_indicator.callbacks.click.register(joystick_indicator_click_callback)
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def _createDataGroup(self):
#         text_widget = TextWidget(widget_id='text_widget', color=[0.3, 0.3, 0.3], font_weight='bold')
#         text_widget.text = 'States'
#         self.data_group.addWidget(text_widget, row=13, column=1, width=10, height=1)
#
#         # Digital numbers
#         self.theta_digital_number = self._add_digital_number(
#             self.data_group,
#             widget_id='theta_dnw',
#             row=14,
#             title='Theta',
#             min_value=-99,
#             max_value=99,
#             increment=0.1,
#             color_ranges=[
#                 {'min': -0.15, 'max': 0.15, 'color': [0, 0.8, 0]}
#             ]
#         )
#         self.v_digital_number = self._add_digital_number(
#             self.data_group,
#             widget_id='v_dnw',
#             row=15,
#             title='V',
#             min_value=-2,
#             max_value=2,
#             increment=0.1,
#         )
#         self.theta_dot_digital_number = self._add_digital_number(
#             self.data_group,
#             widget_id='theta_dot_dnw',
#             row=16,
#             title='Theta Dot',
#             min_value=-999,
#             max_value=999,
#             increment=0.1,
#         )
#         self.psi_dot_digital_number = self._add_digital_number(
#             self.data_group,
#             widget_id='psi_dot_dnw',
#             row=17,
#             title='Psi Dot',
#             min_value=-999,
#             max_value=999,
#             increment=0.1,
#         )
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def _createExperimentGroup(self):
#
#         self.experiment_handler_status_widget = StatusWidget(
#             widget_id='experiment_handler_status_widget',
#             title='Experiment',
#             elements={
#                 'status': StatusWidgetElement(label='Experiment:',
#                                               color=[0, 0.5, 0],
#                                               status='idle',
#                                               ),
#             }
#         )
#
#         self.experiment_group.addWidget(self.experiment_handler_status_widget, row=1, column=1, width=11, height=1)
#
#         def setExperimentHandlerStatus(status: BILBO_ExperimentHandler_Status):
#             match status:
#                 case BILBO_ExperimentHandler_Status.IDLE:
#                     self.experiment_handler_status_widget.elements['status'].status = '---'
#                     self.experiment_handler_status_widget.elements['status'].color = [0.3, 0.3, 0.3]
#                 case BILBO_ExperimentHandler_Status.EXPERIMENT_RUNNING:
#                     self.experiment_handler_status_widget.elements[
#                         'status'].status = f'{type(self.robot.experiment_handler.experiment).__name__}'
#                     self.experiment_handler_status_widget.elements['status'].color = [0, 0.5, 0]
#
#             self.experiment_handler_status_widget.updateConfig()
#
#         setExperimentHandlerStatus(self.robot.experiment_handler.status)
#
#         self.robot.experiment_handler.events.status_changed.on(setExperimentHandlerStatus)
#
#         # Experiment Status
#         self.experiment_status_widget = StatusWidget(
#             widget_id='experiment_status_widget',
#             title='Experiment Status',
#             elements={
#                 'status': StatusWidgetElement(label='Status:',
#                                               color=[0, 0.5, 0],
#                                               status='idle',
#                                               ),
#             }
#         )
#
#         self.experiment_group.addWidget(self.experiment_status_widget, row=2, column=1, width=11, height=1)
#
#         def set_experiment_status(*args, **kwargs):
#             return
#             try:
#                 if self.robot.experiment_handler.experiment is None:
#                     self.experiment_status_widget.elements['status'].status = '---'
#                     self.experiment_status_widget.elements['status'].color = [0.3, 0.3, 0.3]
#                 else:
#                     match self.robot.experiment_handler.experiment.status:
#                         case BILBO_Experiment_Status.NONE:
#                             self.experiment_status_widget.elements['status'].status = '---'
#                             self.experiment_status_widget.elements['status'].color = [0.3, 0.3, 0.3]
#                         case BILBO_Experiment_Status.RUNNING_TRAJECTORY:
#                             self.experiment_status_widget.elements['status'].status = 'running'
#                             self.experiment_status_widget.elements['status'].color = [0, 0.5, 0]
#                         case BILBO_Experiment_Status.CALCULATING:
#                             self.experiment_status_widget.elements['status'].status = 'calculating'
#                             self.experiment_status_widget.elements['status'].color = [0.0, 0.0, 0.5]
#                         case BILBO_Experiment_Status.WAITING_FOR_USER:
#                             self.experiment_status_widget.elements['status'].status = 'waiting for user'
#                             self.experiment_status_widget.elements['status'].color = [184 / 255, 107 / 255, 48 / 255]
#
#                 self.experiment_status_widget.updateConfig()
#             except Exception as e:
#                 ...
#
#         set_experiment_status()
#
#         # self.robot.experiment_handler.events.experiment_status_changed.on(set_experiment_status)
#
#         # Text Widget Showing current trajectory info
#         self.trajectory_info_widget = TextWidget(widget_id='trajectory_info_widget',
#                                                  title='Trajectory Info',
#                                                  horizontal_alignment='left',
#                                                  vertical_alignment='top')
#
#         def setTrajectoryInfo(trajectory: BILBO_InputTrajectory | None):
#             if trajectory is None:
#                 self.trajectory_info_widget.text = f"<strong>Trajectory:</strong> ---"
#                 self.trajectory_info_widget.updateConfig()
#                 return
#
#             self.trajectory_info_widget.text = f"""<strong>Trajectory:</strong> {trajectory.name}
#             <strong>Status:</strong> {'loaded'}
#             <strong>Steps:</strong> {trajectory.length}
#             <strong>Duration:</strong> {trajectory.time_vector[-1]} s"""
#             self.trajectory_info_widget.updateConfig()
#
#         setTrajectoryInfo(self.robot.experiment_handler.current_trajectory)
#
#         # Event Listeners
#
#         def trajectory_started(*args, **kwargs):
#             setTrajectoryInfo(self.robot.experiment_handler.getCurrentTrajectory())
#             self.resume_button.disable()
#             self.abort_button.enable()
#
#         def trajectory_finished(*args, **kwargs):
#             setTrajectoryInfo(None)
#             self.resume_button.disable()
#             self.abort_button.disable()
#
#         def trajectory_stopped(*args, **kwargs):
#             setTrajectoryInfo(None)
#             self.resume_button.disable()
#             self.abort_button.disable()
#
#         def trajectory_loaded(*args, **kwargs):
#             setTrajectoryInfo(self.robot.experiment_handler.getLoadedTrajectory())
#             self.resume_button.enable()
#             self.abort_button.enable()
#
#         self.robot.experiment_handler.events.ll_trajectory_started.on(trajectory_started)
#         self.robot.experiment_handler.events.ll_trajectory_finished.on(trajectory_finished)
#         self.robot.experiment_handler.events.ll_trajectory_aborted.on(trajectory_stopped)
#         self.robot.experiment_handler.events.trajectory_loaded.on(trajectory_loaded)
#
#         self.experiment_group.addWidget(self.trajectory_info_widget, row=8, column=1, width=11, height=3)
#
#         # Loading Bar Indicator
#         self.experiment_progress_bar_indicator = ProgressIndicator(widget_id='experiment_loading_bar_indicator',
#                                                                    track_fill_color=[0.2, 0.5, 0.2],
#                                                                    track_visible=False)
#         self.experiment_progress_bar_indicator.value = 0.5
#
#         self.experiment_group.addWidget(self.experiment_progress_bar_indicator, row=11, column=1, width=11, height=1)
#
#         # Controls
#         self.experiment_control_group = Widget_Group(
#             group_id='experiment_control_group',
#             title='Experiment Control',
#             rows=1,
#             columns=5,
#             show_title=True,
#         )
#         self.experiment_group.addWidget(self.experiment_control_group, row=12, column=1, width=11, height=3)
#
#         self.resume_button = Button(widget_id='resume_button', text='Resume', color=[0.0, 0.4, 0.0])
#         self.resume_button.disable()
#         self.resume_button.callbacks.click.register(self.robot.core.interface_events.resume.set, discard_inputs=True)
#
#         self.experiment_control_group.addWidget(self.resume_button, row=1, column=1, width=1, height=1)
#
#         self.abort_button = Button(widget_id='abort_button', text='Abort', color=[0.4, 0.0, 0.0])
#         self.experiment_control_group.addWidget(self.abort_button, row=1, column=2, width=1, height=1)
#         self.abort_button.disable()
#
#         self.stop_button = Button(widget_id='stop_button', text='Stop Exp', color=[0.4, 0, 0])
#         # self.stop_button.callbacks.click.register(self.robot.experiment_handler.stopExperiment, discard_inputs=True)
#         self.experiment_control_group.addWidget(self.stop_button, row=1, column=5, width=1, height=1)
#
#         self.experiment_apps_group = Widget_Group(
#             group_id='experiment_apps_group',
#             title='Apps',
#             rows=1,
#             columns=5,
#             show_title=True,
#         )
#         self.experiment_group.addWidget(self.experiment_apps_group, row=15, column=1, width=11, height=3)
#
#         dilc_button = Button(widget_id='dilc_button', text='DILC', color=[0.4, 0.4, 0.4])
#         # dilc_button.callbacks.click.register(self.robot.experiments.startDILC)
#         self.experiment_apps_group.addWidget(dilc_button, row=1, column=1, width=1, height=1)
#
#         # def dilc_button_click(*args, **kwargs):
#         #     self.robot.experiment_handler.runExperiment(DILC_Experiment)
#         #     self._openDILCApp()
#
#         # dilc_button.callbacks.click.register(dilc_button_click)
#
#         iml_button = Button(widget_id='iml_button', text='IML', color=[0.4, 0.4, 0.4])
#         self.experiment_apps_group.addWidget(iml_button, row=1, column=2, width=1, height=1)
#         iml_button.disable()
#
#         iitl_button = Button(widget_id='iitl_button', text='IITL', color=[0.4, 0.4, 0.4])
#         self.experiment_apps_group.addWidget(iitl_button, row=1, column=3, width=1, height=1)
#         iitl_button.disable()
#
#         dilc_rls_button = Button(widget_id='dilc_rls_button', text='DILC RLS', color=[0.4, 0.4, 0.4])
#         self.experiment_apps_group.addWidget(dilc_rls_button, row=1, column=4, width=1, height=1)
#         dilc_rls_button.disable()
#
#     # ------------------------------------------------------------------------------------------------------------------
#     # def _openDILCApp(self, *args, **kwargs):
#     #     dilc_app = DILC_App(self.robot)
#     #     dilc_app.open(gui=self.gui)
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def _onDILCExperimentStarted(self, data: DILC_Experiment, *args, **kwargs):
#         self.logger.info("Starting DILC App ... ")
#
#         app = DILC_APP(gui=self.gui, robot=self.robot, experiment=data)
#
#         app.open(gui=self.gui)
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def _streamCallback(self, sample: BILBO_Sample, *args, **kwargs):
#         # Digital numbers
#         self.theta_digital_number.value = np.rad2deg(wrapToPi(sample.lowlevel.estimation.state.theta))
#         self.v_digital_number.value = sample.lowlevel.estimation.state.v
#         self.theta_dot_digital_number.value = np.rad2deg(sample.lowlevel.estimation.state.theta_dot)
#         self.psi_dot_digital_number.value = np.rad2deg(sample.lowlevel.estimation.state.psi_dot)
#
#         # Plots (new API uses set_value)
#         self.theta_timeseries.set_value(sample.lowlevel.estimation.state.theta * 180.0 / 3.141592653589793)
#         self.v_timeseries.set_value(sample.lowlevel.estimation.state.v)
#         self.theta_dot_timeseries.set_value(sample.lowlevel.estimation.state.theta_dot * 180.0 / 3.141592653589793)
#         self.psi_dot_timeseries.set_value(sample.lowlevel.estimation.state.psi_dot * 180.0 / 3.141592653589793)
#
#         # Battery / indicators — throttle to every ~200 ticks
#         if self.robot.core.tick % 200 == 0:
#             voltage = sample.sensors.power.bat_voltage
#             cells = self.robot.config.electronics.battery_cells
#             self.battery_indicator.setValue(percentage=lipo_soc(voltage=voltage, cells=cells), voltage=voltage)
#
#             # Connection
#             signal_strength = sample.connection.strength
#             self.connection_strength_indicator.setValue(self._classify_connection_strength(signal_strength))
#
#             # Internet
#             self.internet_indicator.setValue(sample.connection.internet)
#
#             # Joystick assigned?
#             if js_control is not None:
#                 self.joystick_indicator.setValue(js_control.robotIsAssigned(self.robot) is not None)
#             else:
#                 self.joystick_indicator.setValue(False)
#
#         # TIC (reserved for future logic if needed)


# ======================================================================================================================
class RobotUI:
    _built: bool = False

    plots: list[RT_Plot_Widget]
    overview_page_data: dict

    # === INIT =========================================================================================================
    def __init__(self, robot: BILBO, manager: BILBO_TestbedManager, gui: GUI, app: App):
        self.robot = robot
        self.gui = gui
        self.app = app
        self.manager = manager

        self.pages: Dict[str, Page] = {}
        self.category = Category(id=robot.id, icon='🤖')
        self.gui.categories['robots'].addCategory(self.category)

        self.folder = Folder(folder_id=robot.id)

        self.robot.core.events.stream.on(self.on_robot_stream)
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

        off_button = Button(widget_id='off_button',
                            text="Control Off",
                            color=CONTROL_MODE_COLORS[BILBO_Control_Mode.OFF])
        off_button.callbacks.click.register(self.robot.control.setControlMode, mode=BILBO_Control_Mode.OFF)
        control_group.addWidget(off_button, column=1, width=2, height=2)

        direct_button = Button(widget_id='direct_button', text="Direct",
                               color=CONTROL_MODE_COLORS[BILBO_Control_Mode.DIRECT])
        direct_button.callbacks.click.register(self.robot.control.setControlMode, mode=BILBO_Control_Mode.DIRECT)
        control_group.addWidget(direct_button, column=3, width=2, height=2)

        balancing_button = Button(widget_id='balancing_button', text="Balancing",
                                  color=CONTROL_MODE_COLORS[BILBO_Control_Mode.BALANCING])
        balancing_button.callbacks.click.register(self.robot.control.setControlMode, mode=BILBO_Control_Mode.BALANCING)
        control_group.addWidget(balancing_button, column=5, width=2, height=2)
        velocity_button = Button(widget_id='velocity_button', text="Velocity",
                                 color=CONTROL_MODE_COLORS[BILBO_Control_Mode.VELOCITY])
        velocity_button.callbacks.click.register(self.robot.control.setControlMode, mode=BILBO_Control_Mode.VELOCITY)
        control_group.addWidget(velocity_button, column=7, width=2, height=2)
        position_button = Button(widget_id='position_button', text="Position",
                                 color=CONTROL_MODE_COLORS[BILBO_Control_Mode.POSITION])
        position_button.callbacks.click.register(self.robot.control.setControlMode, mode=BILBO_Control_Mode.POSITION)
        control_group.addWidget(position_button, column=9, width=2, height=2)

        def update_mode_button(mode: BILBO_Control_Mode, *args, **kwargs):
            match mode:
                case BILBO_Control_Mode.OFF:
                    off_button.disable()
                    direct_button.disable()
                    balancing_button.enable()
                    velocity_button.disable()
                    position_button.disable()
                case BILBO_Control_Mode.BALANCING:
                    off_button.enable()
                    direct_button.disable()
                    balancing_button.disable()
                    velocity_button.enable()
                    position_button.enable()
                case BILBO_Control_Mode.VELOCITY:
                    off_button.enable()
                    direct_button.disable()
                    balancing_button.enable()
                    velocity_button.disable()
                    position_button.enable()
                case BILBO_Control_Mode.POSITION:
                    off_button.enable()
                    direct_button.disable()
                    balancing_button.enable()
                    velocity_button.enable()
                    position_button.disable()

        update_mode_button(self.robot.control.mode)
        self.robot.control.events.mode_changed.on(update_mode_button)

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
                tic_button.state='ON'
            else:
                tic_button.state='OFF'

        tic_button.callbacks.click.register(tic_button_clicked)
        self.robot.control.events.tic_mode_changed.on(on_tic_mode_changed)

        control_group.addWidget(tic_button, column=1, row=8, width=2, height=2)

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
        gyro_label = TextWidget(widget_id='gyro_label', text='Gyro (deg/s)', fontSize=10, textColor=[0.7, 0.7, 0.7, 1.0])
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

        testbed_size = self.manager.testbed_config.size
        self.map_widget = MapWidget(widget_id='map_widget',
                                    title='Testbed',
                                    limits={"x": [0, self.manager.testbed_config.size[0]],
                                            "y": [0, self.manager.testbed_config.size[1]]},
                                    initial_display_center=[self.manager.testbed_config.size[0] / 2,
                                                            self.manager.testbed_config.size[1] / 2],
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
            show_name=False
        )
        self.robot_map_agent_tracked.visible = False
        self._tracker_agent_shown = False
        self.map_widget.map.addObject(self.robot_map_agent_tracked)

        def map_double_click(data, *args, **kwargs):
            x = data['x']
            y = data['y']
            safety_margin = 0.2
            if safety_margin < x < testbed_size[0] - safety_margin and safety_margin < y < testbed_size[
                1] - safety_margin:
                self.robot.control.move_to(x, y)
            else:
                self.logger.warning(f"Position out of bounds: {x}, {y}")

        self.map_widget.map.events.double_click.on(map_double_click)

        navigation_group = Widget_Group(widget_id='navigation_group',
                                        title='Navigation',
                                        columns=9,
                                        rows=9,
                                        show_title=True,
                                        )
        page.addWidget(navigation_group, column=22, row=9, width=9, height=10)

        psi_zero_button = Button(widget_id='psi_zero_button', text='Ψ=0', color=[0.4, 0.4, 0.4])
        psi_zero_button.callbacks.click.register(lambda *args, **kwargs: self.robot.control.turn_to(0))
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
        self.control_config_table.add_column(TextColumn(id='parameter', title='Parameter', width=0.5, font_align='left'))
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
        self.config_rows['max_wheel_speed'] = self.config_general_group.make_row(parameter='Max Wheel Speed', value='0.0')
        self.config_rows['max_wheel_torque'] = self.config_general_group.make_row(parameter='Max Wheel Torque', value='0.0')
        self.config_rows['enable_external_inputs'] = self.config_general_group.make_row(parameter='External Inputs', value='disabled')

        # Velocity V PID rows
        self.config_rows['v_kp'] = self.config_velocity_v_group.make_row(parameter='Kp', value='0.0')
        self.config_rows['v_ki'] = self.config_velocity_v_group.make_row(parameter='Ki', value='0.0')
        self.config_rows['v_kd'] = self.config_velocity_v_group.make_row(parameter='Kd', value='0.0')
        self.config_rows['v_kv'] = self.config_velocity_v_group.make_row(parameter='Kv (FF)', value='0.0')
        self.config_rows['v_ka'] = self.config_velocity_v_group.make_row(parameter='Ka (FF)', value='0.0')
        self.config_rows['v_i_term_limit'] = self.config_velocity_v_group.make_row(parameter='I-Term Limit', value='0.0 (disabled)')
        self.config_rows['v_output_limit'] = self.config_velocity_v_group.make_row(parameter='Output Limit', value='0.0 (disabled)')
        self.config_rows['v_d_filter'] = self.config_velocity_v_group.make_row(parameter='D-Filter Td', value='0.0 (disabled)')

        # Velocity Psidot PID rows
        self.config_rows['psidot_kp'] = self.config_velocity_psidot_group.make_row(parameter='Kp', value='0.0')
        self.config_rows['psidot_ki'] = self.config_velocity_psidot_group.make_row(parameter='Ki', value='0.0')
        self.config_rows['psidot_kd'] = self.config_velocity_psidot_group.make_row(parameter='Kd', value='0.0')
        self.config_rows['psidot_kv'] = self.config_velocity_psidot_group.make_row(parameter='Kv (FF)', value='0.0')
        self.config_rows['psidot_ka'] = self.config_velocity_psidot_group.make_row(parameter='Ka (FF)', value='0.0')
        self.config_rows['psidot_i_term_limit'] = self.config_velocity_psidot_group.make_row(parameter='I-Term Limit', value='0.0 (disabled)')
        self.config_rows['psidot_output_limit'] = self.config_velocity_psidot_group.make_row(parameter='Output Limit', value='0.0 (disabled)')
        self.config_rows['psidot_d_filter'] = self.config_velocity_psidot_group.make_row(parameter='D-Filter Td', value='0.0 (disabled)')

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
        if self.robot.core.tick % 5 == 0:  # ~20Hz update rate
            self.robot_map_agent_estimated.update(
                x=sample.estimation.state.x,
                y=sample.estimation.state.y,
                psi=sample.estimation.state.psi
            )

    # ------------------------------------------------------------------------------------------------------------------
    def on_new_tracker_sample(self, sample, *args, **kwargs):
        if not self._built:
            return
        if self.robot.id in self.manager.tracker.robots:
            state = self.manager.tracker.robots[self.robot.id].state

            # Show green (tracked) agent on first tracker sample
            if not self._tracker_agent_shown:
                self.robot_map_agent_tracked.visible = True
                self._tracker_agent_shown = True

            # Update green (tracked) agent from OptiTrack
            self.robot_map_agent_tracked.update(x=state.x, y=state.y, psi=state.psi)

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
            self.config_rows['enable_external_inputs']['value'] = 'enabled' if config.general.enable_external_inputs else 'disabled'

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
                self.psidot_enable_output_limit_checkbox._sendValueToFrontend(self.psidot_enable_output_limit_checkbox._value)
            if self.psidot_enable_d_filter_checkbox._value != config.velocity_control.psidot.pid.enable_d_filter:
                self.psidot_enable_d_filter_checkbox._value = config.velocity_control.psidot.pid.enable_d_filter
                self.psidot_enable_d_filter_checkbox._sendValueToFrontend(self.psidot_enable_d_filter_checkbox._value)

        except Exception as e:
            self.logger.warning(f"Failed to update control config table: {e}")

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
    manager: BILBO_TestbedManager

    @dataclasses.dataclass
    class RobotContainer:
        robot: BILBO_TestbedAgent
        babylon: BabylonBilbo

    robots: dict[str, RobotContainer]

    def __init__(self, manager: BILBO_TestbedManager):
        self.manager = manager

        self.logger = Logger("Testbed Page")
        self.page = Page(id='testbed_page', name='Testbed')
        self.robots = {}

        self._buildPage()

        self.manager.events.new_robot.on(self._on_new_testbed_robot)
        self.manager.events.robot_disconnected.on(self._on_testbed_robot_disconnected)
        self.manager.events.new_tracker_sample.on(self._on_new_tracker_sample)
        self.manager.events.initialized.on(self._on_testbed_initialized)

    # ------------------------------------------------------------------------------------------------------------------
    def _buildPage(self):
        # Statuses
        # Make a group
        # status_group = Widget_Group(group_id='status_group', title='Status', rows=1, columns=1, show_title=True)
        # self.page.addWidget(status_group, row=1, column=1, width=8, height=8)

        self._build_tracker_overview()

        self._build_timecode()

        self.babylon_widget = BabylonWidget(widget_id='babylon_widget')
        self.page.addWidget(self.babylon_widget, row=6, column=30, height=13, width=21)

        self._build_display_group()

    # ------------------------------------------------------------------------------------------------------------------
    def _build_timecode(self):
        # Timecode
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
            # seconds = self.manager.timecode_server.get_time()
            timecode_clock.set(timecode.to_seconds())
            timecode_status_indicator.blink(250)

        if self.manager.timecode_server.status == TimecodeServerStatus.running:
            initialize_timecode()
        else:
            stop_timecode()

        self.manager.timecode_server.events.initialized.on(initialize_timecode)
        self.manager.timecode_server.events.error.on(stop_timecode)
        self.manager.timecode_server.callbacks.zero_frame.register(update_timecode)

        self.page.addWidget(timecode_group, row=13, column=1, width=10, height=2)

    # ------------------------------------------------------------------------------------------------------------------
    def _build_tracker_overview(self):
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

        #

        def initialize_tracker(*args, **kwargs):
            tracker_status.updateConfig(color=[0, 0.8, 0])

            for obj_id, rigid_body in self.manager.tracker.rigid_bodies.items():
                # rb_table.addRow(obj_id, cells=[obj_id, '❌'])
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
        """Build the display/extensions group with display text input and limbo bar slider."""
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
            title_position = 'left',
            inputFieldAlign='center',
            inputFieldFontSize=12,
        )
        display_group.addWidget(self.display_text_input, row=1, column=1, width=2, height=1)

        def on_display_text_changed(text: str):
            self.logger.info(f"Setting display text to: {text}")
            self.manager.extensions.display.set_text(text)

        self.display_text_input.callbacks.value_changed.register(on_display_text_changed)

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

        def on_limbo_height_changed(height: float):
            height_m = height  # Convert cm to mm
            self.logger.info(f"Setting limbo bar height to: {height} mm")
            self.manager.extensions.limbo_bar.setHeight(height_m)

        self.manager.extensions.limbo_bar.setHeight(0)
        self.limbo_height_slider.callbacks.value_changed.register(on_limbo_height_changed)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_new_testbed_robot(self, robot: BILBO_TestbedAgent):
        if robot.id in self.robots:
            self.logger.warning(f'Testbed robot {robot.id} already exists. Skipping.')
            return

        container = self.RobotContainer(
            robot=robot,
            babylon=BabylonBilbo(object_id=robot.id,
                                 color=robot.robot.config.general.color,
                                 text=robot.robot.config.general.short_id)
        )

        self.robots[robot.id] = container
        self.babylon_visualization.addObject(container.babylon)

        # ------------------------------------------------------------------------------------------------------------------

    def _on_testbed_robot_disconnected(self, robot: BILBO_TestbedAgent):
        if robot.id not in self.robots:
            self.logger.warning(f'Testbed robot {robot.id} not found. Skipping.')
            return

        self.babylon_visualization.removeObject(self.robots[robot.id].babylon)
        del self.robots[robot.id]

        # ------------------------------------------------------------------------------------------------------------------

    def _on_new_tracker_sample(self, *args, **kwargs):
        for robot in self.robots.values():
            robot.babylon.set_state(
                x=robot.robot.tracked_object.state.x,
                y=robot.robot.tracked_object.state.y,
                theta=robot.robot.tracked_object.state.theta,
                psi=robot.robot.tracked_object.state.psi,
            )

    # ------------------------------------------------------------------------------------------------------------------
    def _on_testbed_initialized(self, *args, **kwargs):
        # Babylon
        testbed_size = self.manager.testbed_config.size
        self.babylon_visualization = BabylonVisualization(
            id='babylon', babylon_config=
            {
                'title': 'BILBO Testbed',
                'camera': {
                    'target': [testbed_size[0] / 2, testbed_size[1] / 2, 0],
                    'position': [1.5, -0.9, 1.334]
                }
            }
        )

        self.babylon_widget.set_babylon(self.babylon_visualization)
        self.babylon_visualization.start()

        floor = SimpleFloor('floor',
                            size_x=testbed_size[0],
                            size_y=testbed_size[1],
                            origin=self.manager.testbed_config.origin_position)
        self.babylon_visualization.addObject(floor)

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

    # === INIT =========================================================================================================
    def __init__(self, host,
                 testbed_manager: BILBO_TestbedManager,
                 cli: CLI = None,
                 joystick_control: BILBO_JoystickControl = None):
        self.callbacks = BILBO_Application_GUI_Callbacks()

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
        # self.robot_categories = {}
        # self.robot_app_folders = {}
        self.robot_ui = {}

        self._addCategoriesAndPages()

        self._addApplications()

        # self.gui.addApplication(self.example_app)

        self.logger = Logger('gui')

        # Reroute all logs to the CLI
        addLogRedirection(self._logRedirection, minimum_level='INFO')

    # === METHODS ======================================================================================================
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.gui.start()
        self.app.start()

    # ------------------------------------------------------------------------------------------------------------------
    def addRobot(self, robot: BILBO):

        self.robot_ui[robot.id] = RobotUI(robot=robot,
                                          manager=self.testbed_manager,
                                          gui=self.gui,
                                          app=self.app)
        #
        # callout_button = CalloutButton(
        #     text="Go to page",
        #     color=[1, 0, 0]
        # )

        self.gui.callout_handler.add(callout_type=CalloutType.INFO,
                                     title='Robot Connected',
                                     content=f'Robot {robot.id} connected.',
                                     # buttons=[callout_button],
                                     timeout=5)

    # ------------------------------------------------------------------------------------------------------------------
    def removeRobot(self, robot: BILBO):
        self.logger.important(f'Removing robot {robot.id} from GUI')

        self.gui.callout_handler.add(callout_type=CalloutType.WARNING,
                                     title='Robot Disconnected',
                                     content=f'Robot {robot.id} disconnected.',
                                     timeout=5)
        self.robot_ui[robot.id].close()

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
