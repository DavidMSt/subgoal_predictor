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

Usage::

    from master_thesis.scenarios.testbed_importer import load_scenario_yaml

    yaml_text = open("my_testbed_export.yaml").read()
    config = load_scenario_yaml(yaml_text, name="my_scenario")
    config.build(sim)
"""

from __future__ import annotations

import math
import re
from typing import Any

from master_thesis.scenarios.base import (
    AgentSpec,
    ObstacleSpec,
    ScenarioConfig,
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
    parsed = _parse_yaml(yaml_text)
    return _build_config(parsed, name=name, agent_class_name=agent_class_name)


# ---------------------------------------------------------------------------
# YAML parser (no external dependencies)
# ---------------------------------------------------------------------------

def _parse_arr(s: str) -> list[float] | None:
    """Parse ``"[ 1.5 , 2.0 , 0 ]"`` → ``[1.5, 2.0, 0.0]``."""
    if not s:
        return None
    inner = s.strip().lstrip('[').rstrip(']')
    try:
        return [float(v.strip()) for v in inner.split(',') if v.strip()]
    except ValueError:
        return None


def _parse_yaml(text: str) -> dict[str, Any]:
    """Minimal line-by-line parser for the testbed creator YAML format.

    Understands top-level scalar keys (``name:``, ``limits:``), list sections
    (``obstacles:``, ``agents:``, ``tasks:``), the ``assignments:`` mapping
    section, and comment lines.  Produces::

        {
            'name': str,
            'limits': [[xMin, xMax], [yMin, yMax]],
            'obstacles':   [{'obstacle_id': ..., 'x': ..., ...}, ...],
            'agents':      [{'agent_id': ..., 'start_config': [...], ...}, ...],
            'tasks':       [{'task_id': ..., 'x': ..., 'y': ..., 'psi': ...}, ...],
            'assignments': {'agent_id': 'task_id', ...},
        }
    """
    result: dict[str, Any] = {
        'name': 'imported',
        'limits': None,
        'obstacles': [],
        'agents': [],
        'tasks': [],
        'assignments': {},
    }

    # Section headers we recognise (list-of-items sections)
    _SECTIONS = {'obstacles', 'agents', 'tasks'}
    current_section: str | None = None
    current_item: dict | None = None
    limits_list: list[list[float]] = []

    def _flush():
        nonlocal current_item
        if current_item is None:
            return
        sec = current_item.pop('_section', None)
        if sec == 'obstacles':
            result['obstacles'].append(current_item)
        elif sec == 'agents':
            result['agents'].append(current_item)
        elif sec == 'tasks':
            result['tasks'].append(current_item)
        current_item = None

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        # Skip empty lines and full-line comments
        if not stripped or stripped.startswith('#'):
            continue

        # Top-level name
        m = re.match(r'^name:\s*(.+)$', stripped)
        if m:
            result['name'] = m.group(1).strip()
            continue

        # limits section header
        if re.match(r'^\s*limits:\s*$', line):
            _flush()
            current_section = 'limits'
            current_item = None
            continue

        # assignments section header
        if re.match(r'^\s*assignments:\s*$', line):
            _flush()
            current_section = 'assignments'
            current_item = None
            continue

        # List-of-items section headers
        for sec in _SECTIONS:
            if re.match(rf'^\s*{sec}:\s*$', line):
                _flush()
                current_section = sec
                current_item = None
                break
        else:
            # Not a section header → parse content

            if current_section == 'limits':
                # Each limit is a "- [ val , val ]" line
                m2 = re.match(r'^\s*-\s*(\[.+\])\s*$', stripped)
                if m2:
                    arr = _parse_arr(m2.group(1))
                    if arr and len(arr) >= 2:
                        limits_list.append([float(arr[0]), float(arr[1])])
                continue

            if current_section == 'assignments':
                # Each line is "agent_id: task_id"
                m_a = re.match(r'^([\w_-]+):\s*(.+)$', stripped)
                if m_a:
                    result['assignments'][m_a.group(1).strip()] = m_a.group(2).strip()
                continue

            if current_section in _SECTIONS:
                # New list item "- key: value"
                if stripped.startswith('- '):
                    _flush()
                    current_item = {'_section': current_section}
                    rest = stripped[2:].strip()
                    if rest:
                        m3 = re.match(r'^([\w_]+):\s*(.*)$', rest)
                        if m3:
                            current_item[m3.group(1)] = m3.group(2).strip()
                # Key-value continuation
                elif current_item is not None:
                    m4 = re.match(r'^([\w_]+):\s*(.*)$', stripped)
                    if m4:
                        current_item[m4.group(1)] = m4.group(2).strip()

    _flush()

    if len(limits_list) >= 2:
        result['limits'] = limits_list[:2]

    return result


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
    for item in parsed.get('obstacles', []):
        obs = _parse_obstacle(item)
        if obs is not None:
            obstacles.append(obs)

    # Agents
    agents: list[AgentSpec] = []
    for item in parsed.get('agents', []):
        agent = _parse_agent(item, default_class=agent_class_name)
        if agent is not None:
            agents.append(agent)

    # Tasks — auto-assign colors from palette when not specified
    tasks: list[TaskSpec] = []
    for i, item in enumerate(parsed.get('tasks', [])):
        task = _parse_task(item, color_index=i)
        if task is not None:
            tasks.append(task)

    assignments: dict[str, str] = parsed.get('assignments') or {}

    return ScenarioConfig(
        name=cfg_name,
        limits=limits,
        obstacles=obstacles,
        agents=agents,
        tasks=tasks,
        assignments=assignments,
    )


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
        # Circular obstacle — stored as length=radius, width=radius
        r = float(item['radius'])
        return ObstacleSpec(
            obstacle_id=str(obs_id),
            x=x, y=y,
            length=r, width=r,
            psi=0.0,
        )

    # Box / wall obstacle
    length  = float(item.get('length', 0.5))
    width   = float(item.get('width', 0.05))
    psi     = float(item.get('psi', 0.0))
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
    sc_raw = item.get('start_config', '')
    sc = _parse_arr(sc_raw) if isinstance(sc_raw, str) else sc_raw
    start_config: tuple[float, float, float] = (
        float(sc[0]) if sc and len(sc) > 0 else 0.0,
        float(sc[1]) if sc and len(sc) > 1 else 0.0,
        float(sc[2]) if sc and len(sc) > 2 else 0.0,
    )

    # Any extra keys beyond the known fields become agent kwargs.
    # Try to coerce to int/float where possible.
    kwargs: dict = {}
    for k, v in item.items():
        if k in _AGENT_KNOWN_KEYS:
            continue
        if isinstance(v, str):
            try:
                v = int(v)
            except ValueError:
                try:
                    v = float(v)
                except ValueError:
                    pass
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

    # Use shared palette so tasks get consistent colours across the codebase
    color = TASK_COLORS[color_index % len(TASK_COLORS)]

    return TaskSpec(
        task_id=str(task_id),
        x=x, y=y, psi=psi,
        color=color,
    )
