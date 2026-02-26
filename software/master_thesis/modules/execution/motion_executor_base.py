from abc import ABC, abstractmethod
import numpy as np

from master_thesis.containers.general_containers.frodo_agent_container import FRODOAgentContainer
from master_thesis.modules.motion_planning.path_planner_base import PlanResult


class MotionExecutorBase(ABC):
    """Abstract base for motion execution modules."""

    def __init__(self, agent_cont: FRODOAgentContainer, logger):
        self.agent_cont = agent_cont
        self.logger = logger

    @abstractmethod
    def step(self) -> np.ndarray:
        """Return [v, psi_dot] for this timestep."""
        ...

    @abstractmethod
    def set_plan(self, plan_result: PlanResult, phase_key: str = 'default'):
        """Accept a plan result from the path planner."""
        ...

    @abstractmethod
    def is_active(self) -> bool:
        """Whether the executor is currently executing."""
        ...

    @abstractmethod
    def is_goal_reached(self) -> bool:
        """Whether the current target has been reached."""
        ...

    @abstractmethod
    def clear(self):
        """Reset to idle state."""
        ...