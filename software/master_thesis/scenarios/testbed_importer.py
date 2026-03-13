"""Load a testbed-creator YAML export into a :class:`ScenarioConfig`.

The testbed creator (``extensions/testbed_creator``) stores obstacles in a
canvas-rotation convention that differs slightly from :class:`ObstacleSpec`:

* **Testbed** stores ``size: [width, height]`` where *height* is the long axis
  and *width* is the short axis (thickness for walls).  The orientation
  ``psi_testbed`` is a canvas rotation: at ``psi=0`` the long axis points in
  the world +Y direction.

* **ScenarioConfig** uses ``length`` (long axis) / ``width`` (short axis) and
  ``psi_scenario`` where ``psi=0`` means the long axis points in +X.

Conversion::

    psi_scenario = psi_testbed + PI/2      (export  testbed → scenario)
    psi_testbed  = psi_scenario - PI/2     (import  scenario → testbed)

The extended export format produced by the testbed creator is::

    name: my_scenario
    limits:
      - [ xMin , xMax ]
      - [ yMin , yMax ]

    obstacles:
      - obstacle_id: wall-1
        x: 1.5
        y: 0.5
        length: 1.0
        width: 0.05
        psi: 0.0
        height: 1.0

    agents:
      - agent_id: frodo-1
        agent_class_name: FRODOOfflineAgent
        start_config: [ 0.5 , 0.5 , 0.0 ]
        mppi_horizon: 150
        mppi_n_samples: 200

    tasks:
      - task_id: task-1
        x: 2.5
        y: 2.5
        psi: 0.0

    assignments:
      frodo-1: task-1

    gap_geometry:           # optional — used by RL subgoal predictor
      y_wall: 0.0
      gaps:
        - x_center: -0.5
          half_gap: 0.125

Usage::

    from master_thesis.scenarios.testbed_importer import load_scenario_yaml

    yaml_text = open("my_testbed_export.yaml").read()
    config = load_scenario_yaml(yaml_text, name="my_scenario")
    config.build(sim)
"""

from __future__ import annotations

import math
from typing import Any

import yaml

from master_thesis.scenarios.base import (
    AgentSpec,
    ObstacleSpec,
    ScenarioConfig,
    SpawnRegion,
    TASK_COLORS,
    TaskSpec,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_scenario_yaml(
    yaml_text: str,
    name: str | None = None,
    agent_class_name: str = "FRODOOfflineAgent",
) -> ScenarioConfig:
    """Parse a testbed-creator YAML export and return a :class:`ScenarioConfig`.

    Args:
        yaml_text:         Raw YAML string (copied from testbed creator).
        name:              Override the ``name:`` field from the YAML.
                           If *None*, the value in the YAML is used, or
                           ``'imported'`` if absent.
        agent_class_name:  Default agent class when the YAML entry omits
                           ``agent_class_name``.  Defaults to
                           ``'FRODOOfflineAgent'``.

    Returns:
        A fully constructed :class:`ScenarioConfig` ready for ``build(sim)``.
    """
    parsed: dict[str, Any] = yaml.safe_load(yaml_text) or {}
    return _build_config(parsed, name=name, agent_class_name=agent_class_name)


# ---------------------------------------------------------------------------
# ScenarioConfig builder
# ---------------------------------------------------------------------------

def _build_config(
    parsed: dict[str, Any],
    name: str | None,
    agent_class_name: str,
) -> ScenarioConfig:
    cfg_name = name or parsed.get('name') or 'imported'

    # Limits
    raw_limits = parsed.get('limits')
    if raw_limits and len(raw_limits) == 2:
        limits: tuple = (
            (float(raw_limits[0][0]), float(raw_limits[0][1])),
            (float(raw_limits[1][0]), float(raw_limits[1][1])),
        )
    else:
        limits = ((-5.0, 5.0), (-5.0, 5.0))

    # Obstacles
    obstacles: list[ObstacleSpec] = []
    for item in parsed.get('obstacles', []) or []:
        obs = _parse_obstacle(item)
        if obs is not None:
            obstacles.append(obs)

    # Agents
    agents: list[AgentSpec] = []
    for item in parsed.get('agents', []) or []:
        agent = _parse_agent(item, default_class=agent_class_name)
        if agent is not None:
            agents.append(agent)

    # Tasks — auto-assign colors from palette when not specified
    tasks: list[TaskSpec] = []
    for i, item in enumerate(parsed.get('tasks', []) or []):
        task = _parse_task(item, color_index=i)
        if task is not None:
            tasks.append(task)

    assignments: dict[str, str] = parsed.get('assignments') or {}
    gap_geometry: dict | None = parsed.get('gap_geometry')

    agent_region, n_agents = _parse_spawn_region(parsed.get('agent_spawn_region'))
    task_region, n_tasks   = _parse_spawn_region(parsed.get('task_spawn_region'))

    return ScenarioConfig(
        name=cfg_name,
        limits=limits,
        obstacles=obstacles,
        agents=agents,
        tasks=tasks,
        assignments=assignments,
        gap_geometry=gap_geometry,
        agent_spawn_region=agent_region,
        n_agents_random=n_agents,
        task_spawn_region=task_region,
        n_tasks_random=n_tasks,
    )


def _parse_spawn_region(d: dict | None) -> tuple['SpawnRegion | None', int]:
    """Parse a spawn-region dict into a SpawnRegion + count."""
    if not d:
        return None, 0
    return SpawnRegion(
        x_min=float(d.get('x_min', -5)),
        x_max=float(d.get('x_max', 5)),
        y_min=float(d.get('y_min', -5)),
        y_max=float(d.get('y_max', 5)),
    ), int(d.get('n', 0))


def _normalise_psi(psi: float) -> float:
    """Normalise *psi* to ``[-PI, PI]``."""
    psi = math.fmod(psi, 2 * math.pi)
    if psi > math.pi:
        psi -= 2 * math.pi
    elif psi < -math.pi:
        psi += 2 * math.pi
    return psi


def _parse_obstacle(item: dict) -> ObstacleSpec | None:
    obs_id = item.get('obstacle_id') or item.get('id')
    if not obs_id:
        return None

    x = float(item.get('x', 0))
    y = float(item.get('y', 0))

    if 'radius' in item:
        r = float(item['radius'])
        return ObstacleSpec(
            obstacle_id=str(obs_id),
            x=x, y=y,
            length=r, width=r,
            psi=0.0,
        )

    length   = float(item.get('length', 0.5))
    width    = float(item.get('width', 0.05))
    psi      = float(item.get('psi', 0.0))
    v_height = float(item.get('height', 1.0))

    return ObstacleSpec(
        obstacle_id=str(obs_id),
        x=x, y=y,
        length=length,
        width=width,
        psi=_normalise_psi(psi),
        height=v_height,
    )


_AGENT_KNOWN_KEYS = {'agent_id', 'id', 'agent_class_name', 'start_config'}


def _parse_agent(item: dict, default_class: str) -> AgentSpec | None:
    agent_id = item.get('agent_id') or item.get('id')
    if not agent_id:
        return None

    class_name = item.get('agent_class_name') or default_class
    sc_raw = item.get('start_config', [])
    sc = sc_raw if isinstance(sc_raw, (list, tuple)) else [float(v) for v in str(sc_raw).strip('[]').split(',')]
    start_config: tuple[float, float, float] = (
        float(sc[0]) if sc and len(sc) > 0 else 0.0,
        float(sc[1]) if sc and len(sc) > 1 else 0.0,
        float(sc[2]) if sc and len(sc) > 2 else 0.0,
    )

    # Extra keys beyond the known fields become agent kwargs.
    kwargs: dict = {}
    for k, v in item.items():
        if k in _AGENT_KNOWN_KEYS:
            continue
        kwargs[k] = v

    return AgentSpec(
        agent_id=str(agent_id),
        agent_class_name=str(class_name),
        start_config=start_config,
        kwargs=kwargs,
    )


def _parse_task(item: dict, color_index: int) -> TaskSpec | None:
    task_id = item.get('task_id') or item.get('id')
    if not task_id:
        return None

    x   = float(item.get('x', 0))
    y   = float(item.get('y', 0))
    psi = float(item.get('psi', 0))

    color = TASK_COLORS[color_index % len(TASK_COLORS)]

    return TaskSpec(
        task_id=str(task_id),
        x=x, y=y, psi=psi,
        color=color,
    )
