"""Scenario infrastructure: pure-data descriptions that can be applied to any simulation."""

from __future__ import annotations

from dataclasses import dataclass, field


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
    """
    name: str
    limits: tuple[tuple[float, float], tuple[float, float]]
    agents: list[AgentSpec] = field(default_factory=list)
    tasks: list[TaskSpec] = field(default_factory=list)
    obstacles: list[ObstacleSpec] = field(default_factory=list)

    def build(self, sim) -> None:
        """Apply this scenario to *sim* (creates obstacles, agents, tasks)."""
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
                **agent_spec.kwargs,
            )

        for task_spec in self.tasks:
            sim.new_task(
                task_id=task_spec.task_id,
                x=task_spec.x, y=task_spec.y, psi=task_spec.psi,
            )


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
