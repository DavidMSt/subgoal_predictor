# 3rd party
from abc import ABC, abstractmethod
import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class ControllerConfig:
    """Base configuration for local controllers."""
    dt: float = 0.1
    control_limits: Optional[Tuple[Tuple[float, float], Tuple[float, float]]] = None
    # ((v_min, v_max), (psi_dot_min, psi_dot_max))


class LocalController(ABC):
    """
    Abstract base class for reactive/local controllers (MPPI, MPC, ORCA, etc.)

    These controllers compute control inputs online at each timestep,
    as opposed to offline path planners that compute a full trajectory upfront.
    """

    def __init__(self, config: ControllerConfig):
        self.config = config

    @abstractmethod
    def compute_control(
        self,
        state: np.ndarray,
        goal: np.ndarray,
        obstacles: List[np.ndarray],
        other_agents: List[np.ndarray],
    ) -> np.ndarray:
        """
        Compute control input for the current timestep.

        Args:
            state: Current agent state [x, y, psi, v, psi_dot]
            goal: Target position [x, y, psi] (subgoal or final goal)
            obstacles: List of obstacle representations [x, y, radius] each
            other_agents: List of other agent states [x, y, psi, v, psi_dot] each

        Returns:
            Control input [v, psi_dot]
        """
        pass

    @abstractmethod
    def reset(self):
        """Reset controller state (e.g., warm start trajectories)."""
        pass

    def clip_control(self, u: np.ndarray) -> np.ndarray:
        """Clip control to limits if configured."""
        if self.config.control_limits is None:
            return u

        v_limits, psi_dot_limits = self.config.control_limits
        u_clipped = np.array([
            np.clip(u[0], v_limits[0], v_limits[1]),
            np.clip(u[1], psi_dot_limits[0], psi_dot_limits[1])
        ])
        return u_clipped
