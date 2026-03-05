"""Door / narrow-passage scenario for MPPI validation.

The GUI-discoverable version is defined in door_reactive.yaml.
This config function is kept for programmatic use (tests, parameter sweeps).
"""

from __future__ import annotations

import math

from master_thesis.scenarios.base import (
    AgentSpec,
    ObstacleSpec,
    ScenarioConfig,
    TaskSpec,
)


def door_scenario_config(
    door_width: float = 0.8,
    wall_length: float = 4.0,
    wall_thickness: float = 0.2,
    limits: tuple[tuple[float, float], tuple[float, float]] = ((-5, 5), (-5, 5)),
) -> ScenarioConfig:
    """Return a :class:`ScenarioConfig` for two reactive agents crossing a door.

    The wall runs along the x-axis at y = 0 with a gap of *door_width* at x = 0.
    Agent 0 starts below-left, agent 1 starts above-right; their goals are on
    the opposite side.
    """
    half_gap = door_width / 2.0
    half_wall = wall_length / 2.0

    left_cx = -half_gap - half_wall
    right_cx = half_gap + half_wall

    return ScenarioConfig(
        name="door_reactive",
        limits=limits,
        obstacles=[
            ObstacleSpec("door_wall_left", x=left_cx, y=0.0,
                         length=wall_length, width=wall_thickness),
            ObstacleSpec("door_wall_right", x=right_cx, y=0.0,
                         length=wall_length, width=wall_thickness),
        ],
        agents=[
            AgentSpec(
                "agent_0", "FRODOReactiveAgent",
                start_config=(-2.0, -2.0, math.pi / 2),
                kwargs={"mppi_horizon": 150, "mppi_n_samples": 200, "replan_interval": 10},
            ),
            AgentSpec(
                "agent_1", "FRODOReactiveAgent",
                start_config=(2.0, 2.0, -math.pi / 2),
                kwargs={"mppi_horizon": 150, "mppi_n_samples": 200, "replan_interval": 10},
            ),
        ],
        tasks=[
            TaskSpec("task_0", x=-2.0, y=2.0),
            TaskSpec("task_1", x=2.0, y=-2.0),
        ],
    )
