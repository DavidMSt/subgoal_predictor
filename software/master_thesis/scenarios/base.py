"""Scenario infrastructure: pure-data descriptions that can be applied to any simulation."""

from __future__ import annotations

import importlib
import inspect
import pathlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar


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
    agents: list[AgentSpec] = field(default_factory=list)
    tasks: list[TaskSpec] = field(default_factory=list)
    obstacles: list[ObstacleSpec] = field(default_factory=list)
    assignments: dict[str, str] = field(default_factory=dict)  # agent_id → task_id

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

        for task_spec in self.tasks:
            sim.new_task(
                task_id=task_spec.task_id,
                x=task_spec.x, y=task_spec.y, psi=task_spec.psi,
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
    """Import all scenario modules and return one ScenarioConfig per factory.

    Each concrete :class:`ScenarioFactory` subclass found in the scenarios
    package contributes exactly one config via its ``create()`` classmethod.
    Results are sorted alphabetically by ``ScenarioConfig.name``.
    """
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

    configs = []
    for factory in factories:
        try:
            configs.append(factory.create())
        except Exception:
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
