import dataclasses

import qmt

from core.utils.logging_utils import Logger
from core.utils.timecode.timecode import Timecode
from core.utils.timecode.timecode_server import TimecodeServerStatus
from extensions.babylon.src.babylon import BabylonVisualization
from extensions.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo
from extensions.babylon.src.lib.objects.box.box import Box
from extensions.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.gui.src.gui import Page
from extensions.gui.src.lib.objects.objects import Widget_Group
from extensions.gui.src.lib.objects.python.babylon_widget import BabylonWidget
from extensions.gui.src.lib.objects.python.indicators import CircleIndicator
from extensions.gui.src.lib.objects.python.number import DigitalNumberWidget, DigitalClockWidget
from extensions.gui.src.lib.objects.python.sliders import ClassicSliderWidget
from extensions.gui.src.lib.objects.python.table import Table, TextColumn, IndicatorColumn, NumberColumn
from extensions.gui.src.lib.objects.python.text import TextWidget
from extensions.gui.src.lib.objects.python.text_input import InputWidget
from robots.bilbo.testbed.objects import TestbedBILBO, RealTestbedBILBO, BoxObstacle
from robots.bilbo.testbed.testbed_manager import TestbedManager


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
            for bilbo_id, bilbo in self.manager.tracker.bilbos.items():
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
                box.setOrientation(qmt.quatFromAngleAxis(s.psi, [0, 0, 1]))

    # ------------------------------------------------------------------------------------------------------------------
    def _on_obstacle_added(self, obstacle, *args, **kwargs):
        """Add a box obstacle to the Babylon 3D view."""
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
        box.setOrientation(qmt.quatFromAngleAxis(s.psi, [0, 0, 1]))
        self.babylon_visualization.addObject(box)
        self._obstacle_babylon_objects[obs_id] = box

    # ------------------------------------------------------------------------------------------------------------------
    def _on_obstacle_removed(self, obstacle, *args, **kwargs):
        """Remove a box obstacle from the Babylon 3D view."""
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


