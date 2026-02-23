# 3rd party
import numpy as np
from typing import Optional

# bilbolab
from core.utils.logging_utils import Logger

# master thesis
from master_thesis.modules.local_control.local_controller import LocalController
from master_thesis.containers.general_containers.agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.local_world_container import LocalWorldContainer


class LocalControlModule:
    """
    Agent module that wraps a reactive local controller (MPPI, MPC, ORCA, etc.)

    Unlike the EXE module which plays back pre-planned trajectories,
    this module computes controls online at each timestep.

    Usage:
        module = LocalControlModule(agent_cont, MPPIController(config), logger)
        module.set_goal(goal_position)

        # In simulation loop:
        control = module.step(local_world)
    """

    def __init__(
        self,
        agent_cont: FRODOAgentContainer,
        controller: LocalController,
        logger: Logger,
    ):
        """
        Args:
            agent_cont: Agent container with state access
            controller: Local controller instance (MPPI, MPC, etc.)
            logger: Logger instance
        """
        self.agent_cont = agent_cont
        self.controller = controller
        self.logger = logger

        # Current target (subgoal or final goal)
        self._current_goal: Optional[np.ndarray] = None

        # Goal reached threshold
        self.goal_threshold = 0.02  # meters

        self.logger.info(f"LocalControlModule initialized with {controller.__class__.__name__}")

    @property
    def current_goal(self) -> Optional[np.ndarray]:
        """Current target position [x, y, psi]."""
        return self._current_goal

    def set_goal(self, goal: np.ndarray, reset_controller: bool = True):
        """
        Set the current target for the controller.

        Args:
            goal: Target position [x, y, psi] or [x, y]
            reset_controller: Whether to reset controller state (warm start)
        """
        # Ensure goal has psi component
        if len(goal) == 2:
            goal = np.array([goal[0], goal[1], 0.0])
        else:
            goal = np.asarray(goal)

        self._current_goal = goal

        if reset_controller:
            self.controller.reset()

        self.logger.info(f"Goal set to [{goal[0]:.2f}, {goal[1]:.2f}, {goal[2]:.2f}]")

    def clear_goal(self):
        """Clear the current goal."""
        self._current_goal = None
        self.controller.reset()

    def step(self, lwr_cont: LocalWorldContainer) -> np.ndarray:
        """
        Compute control for this timestep.

        Args:
            lwr_cont: Local world container with obstacle and agent info

        Returns:
            Control input [v, psi_dot]
        """
        if self._current_goal is None or self.is_goal_reached():
            return np.zeros(2)  # Idle or arrived

        # Get current state from agent container
        state = np.array([
            self.agent_cont.x,
            self.agent_cont.y,
            self.agent_cont.psi,
            self.agent_cont.state.v,
            self.agent_cont.state.psi_dot,
        ])

        # Extract obstacles from local world
        obstacles = self._get_obstacles(lwr_cont)

        # Extract other agents from local world
        other_agents = self._get_other_agents(lwr_cont)

        # Compute control
        control = self.controller.compute_control(
            state, self._current_goal, obstacles, other_agents
        )

        return control

    def is_goal_reached(self) -> bool:
        """Check if current goal is reached."""
        if self._current_goal is None:
            return False

        pos = np.array([self.agent_cont.x, self.agent_cont.y])
        dist = np.linalg.norm(pos - self._current_goal[:2])
        return dist < self.goal_threshold

    def _get_obstacles(self, lwr_cont: LocalWorldContainer) -> list:
        """
        Extract obstacle positions from local world container.

        Rectangular obstacles (walls) are decomposed into a chain of
        circles along the wall centerline.  Only circles within
        ``obstacle_range`` of the agent are returned so that distant
        walls don't dominate the cost landscape.

        Returns:
            List of [x, y, radius] arrays
        """
        obstacles = []

        if lwr_cont is None:
            return obstacles

        # Proximity filter: only include circles reachable within the
        # MPPI horizon (v_max * H * dt) plus a generous buffer.
        ax, ay = self.agent_cont.x, self.agent_cont.y
        cfg = getattr(self.controller, 'config', None)
        if cfg is not None and cfg.control_limits is not None:
            v_max = max(abs(cfg.control_limits[0][0]), abs(cfg.control_limits[0][1]))
            horizon_reach = v_max * getattr(cfg, 'horizon', 20) * cfg.dt
        else:
            horizon_reach = 2.0
        obs_range = horizon_reach + 0.5  # extra buffer

        if hasattr(lwr_cont, 'obstacles') and lwr_cont.obstacles is not None:
            for obs_id, obs_cont in lwr_cont.obstacles.items():
                if not (hasattr(obs_cont, 'x') and hasattr(obs_cont, 'y')):
                    continue

                shape = getattr(obs_cont, 'shape', 'box')
                length = getattr(obs_cont, 'length', 0.0)
                width = getattr(obs_cont, 'width', 0.0)

                if shape == 'box' and length > 0 and width > 0:
                    psi = getattr(obs_cont, 'psi', 0.0)
                    cx, cy = obs_cont.x, obs_cont.y

                    # Quick reject: skip walls whose center is way out of range
                    if np.hypot(cx - ax, cy - ay) > obs_range + length / 2 + 0.5:
                        continue

                    radius = width / 2.0
                    # Space circles so that adjacent margin zones overlap:
                    # gap = spacing - 2*radius;  margin covers the gap when
                    # spacing <= 2*radius + 2*obstacle_margin.  Use 0.25m
                    # as a good trade-off between coverage and count.
                    spacing = 0.25

                    dx_dir = np.cos(psi)
                    dy_dir = np.sin(psi)

                    n_circles = max(1, int(np.ceil(length / spacing)) + 1)
                    half_length = length / 2.0

                    for i in range(n_circles):
                        t = -half_length + i * spacing
                        if t > half_length:
                            t = half_length
                        px = cx + t * dx_dir
                        py = cy + t * dy_dir
                        if (px - ax) ** 2 + (py - ay) ** 2 <= obs_range ** 2:
                            obstacles.append(np.array([px, py, radius]))
                else:
                    radius = getattr(obs_cont, 'radius', 0.3)
                    if np.hypot(obs_cont.x - ax, obs_cont.y - ay) <= obs_range + radius:
                        obstacles.append(np.array([obs_cont.x, obs_cont.y, radius]))

        return obstacles

    def _get_other_agents(self, lwr_cont: LocalWorldContainer) -> list:
        """
        Extract other agent states from local world container.

        Returns:
            List of [x, y, psi, v, psi_dot] arrays
        """
        other_agents = []

        if lwr_cont is None:
            return other_agents

        # Get neighbor agents from local world
        if hasattr(lwr_cont, 'neighbors') and lwr_cont.neighbors is not None:
            for agent_id, agent_cont in lwr_cont.neighbors.items():
                # Skip self
                if agent_id == self.agent_cont.agent_id:
                    continue

                if hasattr(agent_cont, 'x') and hasattr(agent_cont, 'y'):
                    state = np.array([
                        agent_cont.x,
                        agent_cont.y,
                        getattr(agent_cont, 'psi', 0.0),
                        getattr(agent_cont.state, 'v', 0.0) if hasattr(agent_cont, 'state') else 0.0,
                        getattr(agent_cont.state, 'psi_dot', 0.0) if hasattr(agent_cont, 'state') else 0.0,
                    ])
                    other_agents.append(state)

        return other_agents
