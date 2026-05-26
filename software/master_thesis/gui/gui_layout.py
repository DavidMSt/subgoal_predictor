from __future__ import annotations

import math
from typing import TYPE_CHECKING

from core.utils.callbacks import Callback
from extensions.babylon.src.babylon import BabylonCamera
from extensions.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.gui.src.gui import Category, Page
from extensions.gui.src.lib.objects.python.babylon_widget import BabylonWidget
from extensions.gui.src.lib.objects.python.buttons import Button

from master_thesis.modules.task_assignment.strategies.strategy_registry import StrategyType
from master_thesis.scenarios.base import discover_scenarios
from master_thesis.universal.offline_agent import FRODOOfflineAgent
from master_thesis.universal.reactive_agent import FRODOReactiveAgent

if TYPE_CHECKING:
    from master_thesis.gui.thesis_gui import ThesisGUI


def build_gui(gui: ThesisGUI) -> None:
    widget_width = 4
    widget_height = 2

    cat1 = Category('cat1', max_pages=10)

    # Scenarios page
    page1 = Page('scenarios', grid_size=(22, 50))
    cat1.addPage(page1)

    # Controls page
    page2 = Page('page2', grid_size=(22, 50))
    cat1.addPage(page2)

    # Misc functionality page
    page3 = Page('page3', grid_size=(22, 50))
    cat1.addPage(page3)

    gui.gui.addCategory(cat1)

    # Babylon widget shared across pages
    gui.babylon_widget = BabylonWidget(widget_id='babylon_widget')
    gui.babylon_widget.babylon = gui.babylon_visualization

    page1.addWidget(gui.babylon_widget, row=1, column=1, height=18, width=36)
    page2.addWidget(gui.babylon_widget, row=1, column=1, height=18, width=36)
    page3.addWidget(gui.babylon_widget, row=1, column=1, height=18, width=36)

    # Reset button
    reset_button = Button(text="Reset", callback=gui.reset)
    page1.addWidget(reset_button, height=widget_height, width=widget_width)
    page2.addWidget(reset_button, height=widget_height, width=widget_width)
    page3.addWidget(reset_button, height=widget_height, width=widget_width)

    # Scenario buttons — discovered automatically from master_thesis/scenarios/
    for _config in discover_scenarios():
        page1.addWidget(Button(text=_config.name, callback=Callback(
            function=gui.loadScenario,
            inputs={'config': _config},
            discard_inputs=True,
        )), height=widget_height, width=widget_width)

    # ── Spawn buttons (type-specific) ──────────────────────────────

    page1.addWidget(Button(text="Spawn 3 Offline", callback=Callback(
        function=gui.spawnAgentsAndTasks,
        inputs={'n': 3, 'agent_class': FRODOOfflineAgent},
        discard_inputs=True,
    )), height=widget_height, width=widget_width)

    page1.addWidget(Button(text="Spawn 3 Reactive", callback=Callback(
        function=gui.spawnAgentsAndTasks,
        inputs={'n': 3, 'agent_class': FRODOReactiveAgent},
        discard_inputs=True,
    )), height=widget_height, width=widget_width)

    page1.addWidget(Button(text="Spawn 1+1", callback=Callback(
        function=gui.spawnAgentsAndTasks,
        inputs={'n': 1},
        discard_inputs=True,
    )), height=widget_height, width=widget_width)

    # ── Task Assignment ────────────────────────────────────────────

    page2.addWidget(Button(text="Central TA", callback=Callback(
        function=gui.start_ta_and_show,
        inputs={'strategy': StrategyType.HUNGARIAN},
        discard_inputs=True,
    )), height=widget_height, width=widget_width)

    page2.addWidget(Button(text="Local TA", callback=Callback(
        function=gui.start_ta_and_show,
        inputs={'strategy': StrategyType.GREEDY_NEAREST},
        discard_inputs=True,
    )), height=widget_height, width=widget_width)

    # ── Training-equivalent episodes (match n_subgoals=0 / n_subgoals=1) ──

    page2.addWidget(Button(text="0 Subgoals", callback=Callback(
        function=gui.run_no_subgoal_episode,
        inputs={},
        discard_inputs=True,
    )), height=widget_height, width=widget_width)

    # "1 SG" — staged step: predict subgoals + show markers (no MP, no EXE).
    # Use 'Start MP' then 'Start Execution' as separate follow-up steps.
    page2.addWidget(Button(text="1 Subgoal", callback=Callback(
        function=gui.predict_and_show_subgoals,
        inputs={},
        discard_inputs=True,
    )), height=widget_height, width=widget_width)

    # ── Motion Planning & Execution ────────────────────────────────

    page2.addWidget(Button(text="Start MP", callback=Callback(
        function=gui.start_mp_and_show,
        inputs={},
        discard_inputs=True,
    )), height=widget_height, width=widget_width)

    page2.addWidget(Button(text="Start Execution", callback=Callback(
        function=gui.start_exe_with_recording,
        inputs={},
        discard_inputs=True,
    )), height=widget_height, width=widget_width)

    # ── One-click pipeline: TA → MP → EXE ─────────────────────────

    page2.addWidget(Button(text="Run Pipeline", callback=Callback(
        function=gui.runPipeline,
        inputs={},
        discard_inputs=True,
    )), height=widget_height, width=widget_width)

    page2.addWidget(Button(text="Build Roadmap", callback=Callback(
        function=gui.buildRoadmap,
        inputs={},
        discard_inputs=True,
    )), height=widget_height, width=widget_width)

    # ── Joystick ───────────────────────────────────────────────────

    page3.addWidget(Button(text="Assign Joystick", callback=gui.assignJoystickToFirst),
                    height=2, width=4)

    # ── Visualization controls ─────────────────────────────────────

    page3.addWidget(Button(text="Show Trajectories", callback=Callback(
        function=gui.showTrajectories,
        inputs={},
        discard_inputs=True,
    )), height=widget_height, width=widget_width)

    page3.addWidget(Button(text="Toggle Action Grid", callback=Callback(
        function=gui.toggleActionGrid,
        inputs={},
        discard_inputs=True,
    )), height=widget_height, width=widget_width)

    page3.addWidget(Button(text="Replay Last", callback=Callback(
        function=gui.replay_trajectory,
        inputs={},
        discard_inputs=True,
    )), height=widget_height, width=widget_width)

    # ── Camera presets for screenshots ────────────────────────────
    _cam_presets = [
        BabylonCamera(
            name='Cam Angle',
            target=[0.0, 0.0, 0.0],
            alpha=-0.8958,
            beta=0.8766,
            radius=4.16,
            fov=1.1345,
        ),
        BabylonCamera(
            name='Cam Top',
            target=[0.0, 0.0, 0.0],
            alpha=-1.5670,
            beta=0.0249,
            radius=4.15,
            fov=1.1345,
        ),
    ]

    for _cam in _cam_presets:
        page3.addWidget(Button(text=_cam.name, callback=Callback(
            function=gui.babylon_visualization.animate_camera,
            inputs={'end': _cam, 'duration': 1.5},
            discard_inputs=True,
        )), height=widget_height, width=widget_width)


def build_babylon_floor(gui: ThesisGUI) -> None:
    floor = SimpleFloor('floor', size_y=50, size_x=50, texture='floor_bright.png')
    gui.babylon_visualization.addObject(floor)
