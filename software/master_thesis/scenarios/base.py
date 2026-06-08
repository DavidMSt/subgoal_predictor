"""Scenario infrastructure: pure-data descriptions that can be applied to any simulation."""

from __future__ import annotations

import importlib
import inspect
import pathlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

# ---------------------------------------------------------------------------
# Shared task color palette
# ---------------------------------------------------------------------------

TASK_COLORS: list[list[float]] = [
    [0.902, 0.224, 0.275],  # #E63946 Red
    [0.114, 0.208, 0.341],  # #1D3557 Navy
    [0.000, 0.714, 0.584],  # #00B695 Emerald
    [0.973, 0.647, 0.000],  # #F8A500 Amber
    [0.439, 0.188, 0.627],  # #7030A0 Purple
    [0.000, 0.545, 0.604],  # #008B9A Teal
    [0.933, 0.463, 0.137],  # #EE7623 Orange
    [0.271, 0.482, 0.616],  # #457B9D Steel Blue
    [0.502, 0.502, 0.502],  # #808080 Gray
    [0.659, 0.855, 0.863],  # #A8DADC Light Blue
]


@dataclass
class AgentSpec:
    """Describes one agent to create in a scenario."""
    agent_id: str
    agent_class_name: str  # e.g. "FRODOReactiveAgent" — string keeps it picklable
    start_config: tuple[float, float, float]
    color: tuple[float, float, float] | None = None
    kwargs: dict = field(default_factory=dict)


@dataclass
class TaskSpec:
    """Describes one task to create in a scenario."""
    task_id: str
    x: float
    y: float
    psi: float = 0.0
    color: list[float] | None = None


@dataclass
class ObstacleSpec:
    """Describes one rectangular obstacle (wall segment)."""
    obstacle_id: str
    x: float
    y: float
    length: float
    width: float
    psi: float = 0.0
    height: float = 1.0


@dataclass
class SpawnRegion:
    """Rectangular region for random agent/task spawning."""
    x_min: float
    x_max: float
    y_min: float
    y_max: float


@dataclass
class ScenarioConfig:
    """
    Pure-data scenario description.

    Stores agent class names as *strings* so the config stays picklable
    (required by SB3 ``SubprocVecEnv``).  Classes are resolved lazily in
    :meth:`build`.

    Optional ``assignments`` dict maps agent_id → task_id for scenarios that
    need deterministic task assignment instead of running the TA algorithm.
    Applied automatically at the end of :meth:`build` and via
    :meth:`apply_assignments` for the GUI path.
    """
    name: str
    limits: tuple[tuple[float, float], tuple[float, float]]
    gap_geometry: dict  # {'y_wall': float, 'gaps': list[dict]}
    agents: list[AgentSpec] = field(default_factory=list)
    tasks: list[TaskSpec] = field(default_factory=list)
    obstacles: list[ObstacleSpec] = field(default_factory=list)
    assignments: dict[str, str] = field(default_factory=dict)  # agent_id → task_id
    agent_spawn_region: SpawnRegion | None = None  # if set, spawn n_agents_random agents randomly in this region
    task_spawn_region: SpawnRegion | None = None   # if set, spawn n_tasks_random tasks randomly in this region
    n_agents_random: int = 0
    n_tasks_random: int = 0
    subgoal_limits: tuple[tuple[float, float], tuple[float, float]] | None = None  # optional clip for action grid

    def build(self, sim, log_level: str = 'INFO') -> None:
        """Apply this scenario to *sim* (creates obstacles, agents, tasks).

        Args:
            log_level: Logger level for spawned agents. Use 'WARNING' to
                suppress verbose per-step output during RL training.
        """
        sim.environment.set_limits(limits=self.limits)

        for obs in self.obstacles:
            sim.new_obstacle(
                obstacle_id=obs.obstacle_id,
                x=obs.x, y=obs.y, psi=obs.psi,
                length=obs.length, width=obs.width, height=obs.height,
            )

        for agent_spec in self.agents:
            agent_cls = _resolve_agent_class(agent_spec.agent_class_name)
            sim.new_agent(
                agent_id=agent_spec.agent_id,
                agent_class=agent_cls,
                start_config=agent_spec.start_config,
                color=agent_spec.color or (1.0, 1.0, 1.0),
                log_level=log_level,
                **agent_spec.kwargs,
            )

        if self.agent_spawn_region is not None and self.n_agents_random > 0:
            r = self.agent_spawn_region
            agent_cls = _resolve_agent_class(
                self.agents[0].agent_class_name if self.agents else 'FRODOOfflineAgent'
            )
            sim.spawn_agents(
                n=self.n_agents_random, agent_class=agent_cls, log_level=log_level,
                x_bounds=(r.x_min, r.x_max), y_bounds=(r.y_min, r.y_max),
            )

        for task_spec in self.tasks:
            sim.new_task(
                task_id=task_spec.task_id,
                x=task_spec.x, y=task_spec.y, psi=task_spec.psi,
            )

        if self.task_spawn_region is not None and self.n_tasks_random > 0:
            r = self.task_spawn_region
            sim.spawn_tasks(
                n=self.n_tasks_random,
                x_bounds=(r.x_min, r.x_max), y_bounds=(r.y_min, r.y_max),
            )

        self.apply_assignments(sim)

    def apply_assignments(self, sim) -> None:
        """Directly assign tasks to agents, bypassing the TA algorithm.

        Looks up each agent and task by ID in *sim* and sets the assignment
        on the agent's TA container.  Silently skips unknown IDs.
        Only applies to agents that have a TA module (universal agents).
        """
        if not self.assignments:
            return

        env_cont = sim.environment.environment_container
        for agent_id, task_id in self.assignments.items():
            agent = sim.agents.get(agent_id)
            task_cont = env_cont.state.task_conts.get(task_id)
            if agent is None or task_cont is None:
                continue
            if not hasattr(agent, 'tam'):
                continue
            agent.tam.ta_container.assigned_task = task_cont


# ---------------------------------------------------------------------------
# Scenario factory ABC
# ---------------------------------------------------------------------------

class ScenarioFactory(ABC):
    """Abstract base class for GUI-discoverable scenario factories.

    Subclass this in any ``master_thesis/scenarios/*.py`` file to have the
    scenario appear automatically as a button in the GUI.

    Required:
        name (ClassVar[str]): Label shown on the GUI button.

    Must implement:
        create() -> ScenarioConfig
    """

    name: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        # Only enforce on concrete (fully implemented) subclasses.
        if not inspect.isabstract(cls) and not hasattr(cls, "name"):
            raise TypeError(
                f"Concrete ScenarioFactory subclass '{cls.__name__}' "
                "must define a 'name' class variable."
            )

    @classmethod
    @abstractmethod
    def create(cls) -> ScenarioConfig:
        """Return the ScenarioConfig for this scenario."""
        ...


# ---------------------------------------------------------------------------
# Scenario discovery
# ---------------------------------------------------------------------------

_SCENARIOS_DIR = pathlib.Path(__file__).parent
_SKIP_FILES = {"base.py", "__init__.py"}


def _all_subclasses(cls: type) -> list[type]:
    result = []
    for sub in cls.__subclasses__():
        result.append(sub)
        result.extend(_all_subclasses(sub))
    return result


def discover_scenarios() -> list[ScenarioConfig]:
    """Discover all scenarios and return one :class:`ScenarioConfig` per entry.

    Two sources are combined:

    * **Python** — every ``*.py`` file in the scenarios package is imported;
      each concrete :class:`ScenarioFactory` subclass contributes one config.
    * **YAML** — every ``*.yaml`` file in the scenarios package is loaded via
      :func:`master_thesis.scenarios.testbed_importer.load_scenario_yaml`.

    Results are sorted alphabetically by ``ScenarioConfig.name``.
    """
    # --- Python factories ---
    for path in sorted(_SCENARIOS_DIR.glob("*.py")):
        if path.name in _SKIP_FILES:
            continue
        try:
            importlib.import_module(f"master_thesis.scenarios.{path.stem}")
        except Exception:
            pass

    factories = [
        cls for cls in _all_subclasses(ScenarioFactory)
        if not inspect.isabstract(cls)
    ]

    configs: list[ScenarioConfig] = []
    for factory in factories:
        try:
            configs.append(factory.create())
        except Exception:
            pass

    # --- YAML scenarios ---
    try:
        from master_thesis.scenarios.testbed_importer import load_scenario_yaml
        for yaml_path in sorted(_SCENARIOS_DIR.glob("*.yaml")):
            try:
                cfg = load_scenario_yaml(yaml_path.read_text(encoding="utf-8"))
                configs.append(cfg)
            except Exception:
                pass
    except ImportError:
        pass

    configs.sort(key=lambda c: c.name)
    return configs


# ---------------------------------------------------------------------------
# Lazy class resolution
# ---------------------------------------------------------------------------

_AGENT_CLASS_REGISTRY: dict[str, type] = {}


def _resolve_agent_class(class_name: str) -> type:
    """Import and return the agent class for *class_name*."""
    if class_name in _AGENT_CLASS_REGISTRY:
        return _AGENT_CLASS_REGISTRY[class_name]

    # Map of known agent class names → module paths
    _KNOWN = {
        "FRODOUniversalAgent": "master_thesis.universal.universal_agent",
        "FRODOOfflineAgent":   "master_thesis.universal.offline_agent",
        "FRODOReactiveAgent":  "master_thesis.universal.reactive_agent",
        "FRODORLAgent":        "master_thesis.universal.rl_agent",
        "FRODOGeneralAgent":   "master_thesis.general.general_agent",
    }

    module_path = _KNOWN.get(class_name)
    if module_path is None:
        raise ValueError(
            f"Unknown agent class '{class_name}'. "
            f"Known classes: {list(_KNOWN.keys())}"
        )

    import importlib
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    _AGENT_CLASS_REGISTRY[class_name] = cls
    return cls
