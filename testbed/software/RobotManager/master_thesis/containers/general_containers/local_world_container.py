from dataclasses import dataclass, field
from master_thesis.containers.base_container import BaseContainer
from master_thesis.containers.general_containers.agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.obstacle_container import ObstacleContainer
from master_thesis.containers.general_containers.task_container import TaskContainer

# ---------------------------------------------------------------------------
# LocalWorldConfig:
# Controls what the agent is able to perceive.
# None = infinite range (see all)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class LocalWorldConfig:
    ...


# ---------------------------------------------------------------------------
# LocalWorldState:
# What the agent *perceives* about the external world.
# No self-agent duplication. Only external entities.
# ---------------------------------------------------------------------------

@dataclass(frozen=False, slots=False)
class LocalWorldState:
    neighbors: dict[str, FRODOAgentContainer] = field(default_factory=dict)
    tasks: dict[str, TaskContainer] = field(default_factory=dict)
    obstacles: dict[str, ObstacleContainer] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# LocalWorldContainer:
# Bonds config + state, and is attached to each agent.
# ---------------------------------------------------------------------------

@dataclass(frozen=False, slots=False)
class LocalWorldContainer(BaseContainer):
    config: LocalWorldConfig = field(default_factory= LocalWorldConfig)
    state: LocalWorldState = field(default_factory=LocalWorldState)