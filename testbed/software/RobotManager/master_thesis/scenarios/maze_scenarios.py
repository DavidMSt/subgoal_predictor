"""Maze scenarios: 2x2 single-agent and 4x4 multi-agent."""

from __future__ import annotations

import math

from master_thesis.scenarios.base import (
    AgentSpec,
    ObstacleSpec,
    ScenarioConfig,
    TaskSpec,
)

_HALF_PI = math.pi / 2


def maze_2x2_config(
    wall_thickness: float = 0.1,
    agent_class: str = "FRODOOfflineAgent",
) -> ScenarioConfig:
    """Return a :class:`ScenarioConfig` for a 2x2 m single-agent maze.

    Agent starts bottom-left, goal is top-right.
    """
    return ScenarioConfig(
        name="maze_2x2",
        limits=((-1, 1), (-1, 1)),
        obstacles=[
            # Outer boundary
            ObstacleSpec("wall_top",    x=0.0,  y=1.0,  length=2.0, width=wall_thickness),
            ObstacleSpec("wall_bottom", x=0.0,  y=-1.0, length=2.0, width=wall_thickness),
            ObstacleSpec("wall_left",   x=-1.0, y=0.0,  length=2.0, width=wall_thickness, psi=_HALF_PI),
            ObstacleSpec("wall_right",  x=1.0,  y=0.0,  length=2.0, width=wall_thickness, psi=_HALF_PI),
            # Internal walls
            ObstacleSpec("maze_1",  x=-0.5,  y=0.5,   length=0.5, width=wall_thickness, psi=_HALF_PI),
            ObstacleSpec("maze_2",  x=-0.25, y=0.5,   length=0.5, width=wall_thickness),
            ObstacleSpec("maze_3",  x=0.0,   y=0.25,  length=0.5, width=wall_thickness, psi=_HALF_PI),
            ObstacleSpec("maze_4",  x=0.5,   y=0.5,   length=0.5, width=wall_thickness),
            ObstacleSpec("maze_5",  x=-0.5,  y=-0.25, length=0.5, width=wall_thickness, psi=_HALF_PI),
            ObstacleSpec("maze_6",  x=0.0,   y=0.0,   length=0.5, width=wall_thickness),
            ObstacleSpec("maze_7",  x=0.5,   y=-0.25, length=0.5, width=wall_thickness, psi=_HALF_PI),
            ObstacleSpec("maze_8",  x=-0.25, y=-0.5,  length=0.5, width=wall_thickness),
            ObstacleSpec("maze_9",  x=0.0,   y=-0.75, length=0.5, width=wall_thickness, psi=_HALF_PI),
            ObstacleSpec("maze_10", x=0.5,   y=-0.5,  length=0.5, width=wall_thickness),
        ],
        agents=[
            AgentSpec("frodo1", agent_class, start_config=(-0.75, -0.75, 0.0)),
        ],
        tasks=[
            TaskSpec("goal1", x=0.75, y=0.75, color=[0, 1, 0]),
        ],
    )


def maze_4x4_config(
    wall_thickness: float = 0.1,
    agent_class: str = "FRODOOfflineAgent",
) -> ScenarioConfig:
    """Return a :class:`ScenarioConfig` for a 4x4 m three-agent maze.

    Three agents start at the top; three goals are at the bottom.
    """
    return ScenarioConfig(
        name="maze_4x4",
        limits=((-2, 2), (-2, 2)),
        obstacles=[
            # Outer boundary
            ObstacleSpec("wall_top",    x=0.0,  y=2.0,  length=4.0, width=wall_thickness),
            ObstacleSpec("wall_bottom", x=0.0,  y=-2.0, length=4.0, width=wall_thickness),
            ObstacleSpec("wall_left",   x=-2.0, y=0.0,  length=4.0, width=wall_thickness, psi=_HALF_PI),
            ObstacleSpec("wall_right",  x=2.0,  y=0.0,  length=4.0, width=wall_thickness, psi=_HALF_PI),
            # Top row (y=1.5)
            ObstacleSpec("maze_1",  x=-1.25, y=1.5,   length=1.0, width=wall_thickness, psi=_HALF_PI),
            ObstacleSpec("maze_2",  x=0.0,   y=1.5,   length=1.0, width=wall_thickness),
            ObstacleSpec("maze_3",  x=1.25,  y=1.5,   length=1.0, width=wall_thickness, psi=_HALF_PI),
            # Upper-middle row (y=0.75)
            ObstacleSpec("maze_4",  x=-1.5,  y=0.75,  length=0.5, width=wall_thickness),
            ObstacleSpec("maze_5",  x=-0.5,  y=0.75,  length=1.0, width=wall_thickness, psi=_HALF_PI),
            ObstacleSpec("maze_6",  x=0.5,   y=0.75,  length=1.0, width=wall_thickness),
            ObstacleSpec("maze_7",  x=1.5,   y=0.75,  length=1.0, width=wall_thickness, psi=_HALF_PI),
            # Center row (y=0.0)
            ObstacleSpec("maze_8",  x=-1.0,  y=0.0,   length=1.0, width=wall_thickness, psi=_HALF_PI),
            ObstacleSpec("maze_9",  x=0.0,   y=0.0,   length=1.0, width=wall_thickness),
            ObstacleSpec("maze_10", x=1.0,   y=0.0,   length=1.0, width=wall_thickness, psi=_HALF_PI),
            # Lower-middle row (y=-0.75)
            ObstacleSpec("maze_11", x=-1.5,  y=-0.75, length=1.0, width=wall_thickness, psi=_HALF_PI),
            ObstacleSpec("maze_12", x=-0.5,  y=-0.75, length=1.0, width=wall_thickness),
            ObstacleSpec("maze_13", x=0.5,   y=-0.75, length=1.0, width=wall_thickness, psi=_HALF_PI),
            ObstacleSpec("maze_14", x=1.5,   y=-0.75, length=0.5, width=wall_thickness),
            # Bottom row (y=-1.5)
            ObstacleSpec("maze_15", x=-1.25, y=-1.5,  length=1.0, width=wall_thickness, psi=_HALF_PI),
            ObstacleSpec("maze_16", x=0.0,   y=-1.5,  length=1.0, width=wall_thickness),
            ObstacleSpec("maze_17", x=1.25,  y=-1.5,  length=1.0, width=wall_thickness, psi=_HALF_PI),
        ],
        agents=[
            AgentSpec("frodo1", agent_class, start_config=(-1.75, 1.75, 0.0)),
            AgentSpec("frodo2", agent_class, start_config=(0.0, 1.75, 0.0)),
            AgentSpec("frodo3", agent_class, start_config=(1.75, 1.75, 0.0)),
        ],
        tasks=[
            TaskSpec("goal1", x=-1.75, y=-1.75, color=[0, 1, 0]),
            TaskSpec("goal2", x=0.0,   y=-1.75, color=[1, 1, 0]),
            TaskSpec("goal3", x=1.75,  y=-1.75, color=[0, 0, 1]),
        ],
    )
