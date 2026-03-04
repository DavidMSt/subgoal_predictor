"""Collision-prevention verification scenarios.

Load them in the GUI via the auto-discovered scenario buttons, then press
Central TA → Run Pipeline to watch the collision prevention in action.
"""

from __future__ import annotations

import math

from master_thesis.scenarios.base import (
    AgentSpec,
    ObstacleSpec,
    ScenarioConfig,
    ScenarioFactory,
    TaskSpec,
)


class CollisionAgentsScenario(ScenarioFactory):
    """Two offline agents on a direct collision course.

    Each agent is pre-assigned to the task at the other agent's starting
    position, forcing them to head straight at each other.  Without direct
    assignment the TA algorithm would assign each agent its nearest task
    (distance 0) and no one would move.

    Expected behaviour:
    - Collision prevention fires as they approach → both stop for one tick
    - Each replans around the other (freeze-and-plan)
    - Both reach their goals without passing through each other
    Watch the console for replan logs.
    """

    name = "collision_agents"

    @classmethod
    def create(cls) -> ScenarioConfig:
        return ScenarioConfig(
            name=cls.name,
            limits=((-4, 4), (-4, 4)),
            agents=[
                AgentSpec("vfrodo0", "FRODOOfflineAgent", start_config=(-2.0, 0.0, 0.0)),
                AgentSpec("vfrodo1", "FRODOOfflineAgent", start_config=(2.0, 0.0, math.pi)),
            ],
            tasks=[
                TaskSpec("task_right", x=2.0,  y=0.0),
                TaskSpec("task_left",  x=-2.0, y=0.0),
            ],
            assignments={
                "vfrodo0": "task_right",   # agent on the left → goes right
                "vfrodo1": "task_left",    # agent on the right → goes left
            },
        )


class JoystickWallTest(ScenarioFactory):
    """Manual joystick-driving test: one driveable agent, one autonomous agent, one wall.

    Layout (2x2 m arena):
      - Horizontal wall at y=0 blocking the centre
      - frodo0 at (0, -1) facing north → assign joystick to this one and drive into the wall
      - frodo1 at (-1.5, 0.8) facing east → pre-assigned to task_right
      - task_right at (1.5, 0.8) on the open side

    Use this to test:
      - Does the wall stop the joystick-driven agent?
      - Does the autonomous agent plan around the wall correctly?
    """

    name = "joystick_wall_test"

    @classmethod
    def create(cls) -> ScenarioConfig:
        return ScenarioConfig(
            name=cls.name,
            limits=((-2, 2), (-2, 2)),
            obstacles=[
                ObstacleSpec("wall_centre", x=0.0, y=0.0, length=3.0, width=0.2),
            ],
            agents=[
                AgentSpec("frodo0", "FRODOOfflineAgent", start_config=(0.0, -1.0, math.pi / 2)),
                AgentSpec("frodo1", "FRODOOfflineAgent", start_config=(-1.5, 0.8, 0.0)),
            ],
            tasks=[
                TaskSpec("task_right", x=1.5, y=0.8),
            ],
            assignments={
                "frodo0": "task_right",
            },
        )


class CollisionWallScenario(ScenarioFactory):
    """Single offline agent that must navigate around a blocking wall.

    A vertical wall sits at x=0 spanning y=-2 to y=2, blocking the direct
    path from the agent (y=-2.5) to its task (y=2.5).  Expected:
    - OMPL plans a path around the wall
    - Collision prevention fires if the agent ever tries to step into the wall
    """

    name = "collision_wall"

    @classmethod
    def create(cls) -> ScenarioConfig:
        return ScenarioConfig(
            name=cls.name,
            limits=((-4, 4), (-4, 4)),
            obstacles=[
                ObstacleSpec("wall", x=0.0, y=0.0, psi=math.pi / 2, length=4.0, width=0.2),
            ],
            agents=[
                AgentSpec("vfrodo0", "FRODOOfflineAgent", start_config=(0.0, -2.5, math.pi / 2)),
            ],
            tasks=[
                TaskSpec("task0", x=0.0, y=2.5),
            ],
        )
