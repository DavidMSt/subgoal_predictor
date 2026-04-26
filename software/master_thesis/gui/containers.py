from __future__ import annotations

import dataclasses

from extensions.babylon.src.lib.objects.box.box import WallFancy
from extensions.babylon.src.lib.objects.drawings import CircleDrawing
from extensions.babylon.src.lib.objects.frodo.frodo import BabylonFrodo
from extensions.joystick.joystick_manager import Joystick
from simulation.core.scheduling import Action

from master_thesis.general.general_obstacle import GeneralObstacle
from master_thesis.general.general_task import GeneralTask
from master_thesis.universal.offline_agent import FRODOOfflineAgent
from master_thesis.universal.reactive_agent import FRODOReactiveAgent
from master_thesis.universal.rl_agent import FRODORLAgent
from master_thesis.universal.universal_agent import FRODOUniversalAgent


class BabylonTask(CircleDrawing):
    """
    Babylon task visualization that inherits from CircleDrawing.
    Visualized as a flat, semi-transparent solid circle with a thin border.
    Reduced size: radius 0.16 (20% smaller than 0.2).
    """
    def __init__(self, object_id: str, x, y, color):
        r, g, b = color[:3]
        super().__init__(
            object_id,
            x=x, y=y,
            radius=0.16,
            fill_color=[r, g, b, 0.4],
            border_color=[r, g, b, 1.0],
            border_width=0.01,
        )
        self.config['color'] = color

    def setColor(self, color: list):
        """
        Dynamically update the task color.

        Args:
            color: RGB color as [r, g, b] with values 0-1
        """
        self.config['color'] = color
        r, g, b = color[:3]
        super().setColor(fill_rgba=[r, g, b, 0.4], border_rgba=[r, g, b, 1.0])


# Agent type → Babylon color
AGENT_TYPE_COLORS: dict[type, list[float]] = {
    FRODOOfflineAgent:  [0.3, 0.5, 1.0],   # blue
    FRODOReactiveAgent: [0.3, 1.0, 0.5],   # green
    FRODORLAgent:       [0.7, 0.3, 1.0],   # purple
}


@dataclasses.dataclass
class RobotGUIContainer:
    babylon: BabylonFrodo
    sim_agent: FRODOUniversalAgent
    assignment_circle: CircleDrawing | None = None
    trajectory_lines: list = dataclasses.field(default_factory=list)
    subgoal_markers: list = dataclasses.field(default_factory=list)
    waypoint_markers: list = dataclasses.field(default_factory=list)
    _last_plan_result: object = None
    _last_trajectory_update: float = 0.0
    joystick: Joystick | None = None
    _joystick_action: Action | None = None
    _last_assigned_task_id: str | None = None
    _alert_active: bool = False
    _original_color: list = dataclasses.field(default_factory=lambda: [1.0, 1.0, 1.0])


@dataclasses.dataclass
class ObstacleGUIContainer:
    babylon: WallFancy | None
    sim_obstacle: GeneralObstacle


@dataclasses.dataclass
class TaskGUIContainer:
    babylon: CircleDrawing | None
    sim_task: GeneralTask
