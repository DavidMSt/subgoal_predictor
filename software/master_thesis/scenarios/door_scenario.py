"""Door / narrow-passage scenario for MPPI validation and RL training.

The GUI-discoverable version is defined in door_reactive.yaml.
This config function is kept for programmatic use (tests, parameter sweeps).
"""

from __future__ import annotations

import math

from master_thesis.scenarios.base import (
    AgentSpec,
    ObstacleSpec,
    ScenarioConfig,
    ScenarioFactory,
    SpawnRegion,
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


def gap_rl_scenario_config(
    n_agents: int = 3,
    door_width: float = 0.8,
    wall_length: float = 4.0,
    wall_thickness: float = 0.2,
    limits: tuple[tuple[float, float], tuple[float, float]] = ((-5, 5), (-5, 5)),
) -> ScenarioConfig:
    """Gap scenario designed for RL subgoal training.

    Wall at y = 0 with a single gap of *door_width* at x = 0.
    Tasks are fixed on the far side (y > 0), spread evenly in x so their
    positions are never in or near the gap.  Agents are spawned randomly on
    the near side (y < 0) every episode, giving variety in approach angle
    and distance without affecting what the policy needs to learn (gap
    coordination happens before the gap, task positions beyond it don't
    matter for that behaviour).
    """
    half_gap = door_width / 2.0
    half_wall = wall_length / 2.0

    left_cx  = -half_gap - half_wall
    right_cx =  half_gap + half_wall

    x_min, x_max = limits[0]
    y_min, y_max = limits[1]

    # Tasks spread evenly across the far side, well away from the gap.
    if n_agents == 1:
        task_xs = [0.0]
    else:
        step = (x_max - x_min - 2.0) / (n_agents - 1)
        task_xs = [x_min + 1.0 + i * step for i in range(n_agents)]

    tasks = [
        TaskSpec(f"task_{i}", x=round(x, 3), y=y_max * 0.6)
        for i, x in enumerate(task_xs)
    ]

    return ScenarioConfig(
        name="gap_rl",
        limits=limits,
        obstacles=[
            ObstacleSpec("gap_wall_left",  x=left_cx,  y=0.0,
                         length=wall_length, width=wall_thickness),
            ObstacleSpec("gap_wall_right", x=right_cx, y=0.0,
                         length=wall_length, width=wall_thickness),
        ],
        tasks=tasks,
        gap_geometry={'half_gap': half_gap, 'x_center': 0.0, 'y_wall': 0.0},
        # Agents spawn randomly on the near side each episode.
        agent_spawn_region=SpawnRegion(
            x_min=x_min + 0.5,
            x_max=x_max - 0.5,
            y_min=y_min + 0.5,
            y_max=-0.5,
        ),
        n_agents_random=n_agents,
    )


class GapRLScenarioFactory(ScenarioFactory):
    """GUI-discoverable factory for the gap RL training scenario."""
    name = "Gap RL"

    @classmethod
    def create(cls) -> ScenarioConfig:
        return gap_rl_scenario_config()


def two_gap_rl_scenario_config(
    n_agents: int = 5,
    limits: tuple[tuple[float, float], tuple[float, float]] = ((-1, 1), (-1, 1)),
) -> ScenarioConfig:
    """2×2 two-gap scenario for RL subgoal training.

    Mirrors the rl_5n_random_2x2.yaml layout but with:
    - Tasks fixed in a single row at y=-0.7 (no randomness)
    - gap_geometry metadata for the dist_to_gap observation feature
    - Agent spawn region in the upper half (y > 0)

    The horizontal wall at y=0 has two gaps at x≈±0.5 (each 0.25m wide).
    """
    x_min, x_max = limits[0]
    y_min, y_max = limits[1]

    # Fixed tasks evenly spread across the bottom, avoiding gap columns
    step = 1.4 / (n_agents - 1) if n_agents > 1 else 0.0
    task_xs = [-0.7 + i * step for i in range(n_agents)]

    tasks = [
        TaskSpec(f"task_{i}", x=round(x, 3), y=-0.7)
        for i, x in enumerate(task_xs)
    ]

    return ScenarioConfig(
        name="two_gap_rl",
        limits=limits,
        obstacles=[
            # Boundary walls
            ObstacleSpec("boundary_top",    x=0.0,  y=1.0,  length=2.0, width=0.05, psi=0.0),
            ObstacleSpec("boundary_right",  x=1.0,  y=0.0,  length=2.0, width=0.05, psi=-math.pi / 2),
            ObstacleSpec("boundary_bottom", x=0.0,  y=-1.0, length=2.0, width=0.05, psi=math.pi),
            ObstacleSpec("boundary_left",   x=-1.0, y=0.0,  length=2.0, width=0.05, psi=math.pi / 2),
            # Middle wall — three segments, leaving gaps at x≈±0.5
            ObstacleSpec("mid_left",   x=-0.8125, y=0.0, length=0.375, width=0.05, psi=0.0),
            ObstacleSpec("mid_center", x=0.0,     y=0.0, length=0.75,  width=0.05, psi=0.0),
            ObstacleSpec("mid_right",  x=0.8125,  y=0.0, length=0.375, width=0.05, psi=0.0),
        ],
        tasks=tasks,
        gap_geometry={
            'gaps': [
                {'x_center': -0.5, 'half_gap': 0.125},
                {'x_center':  0.5, 'half_gap': 0.125},
            ],
            'y_wall': 0.0,
        },
        agent_spawn_region=SpawnRegion(
            x_min=x_min + 0.125,
            x_max=x_max - 0.125,
            y_min=0.125,
            y_max=y_max - 0.125,
        ),
        n_agents_random=n_agents,
    )


class TwoGapRLScenarioFactory(ScenarioFactory):
    """GUI-discoverable factory for the two-gap 2×2 RL training scenario."""
    name = "Two Gap RL"

    @classmethod
    def create(cls) -> ScenarioConfig:
        return two_gap_rl_scenario_config()
