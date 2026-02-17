# 3rd party
import numpy as np
from typing import List, Callable, Optional, Tuple
from dataclasses import dataclass, field

# master thesis
from master_thesis.modules.local_control.local_controller import LocalController, ControllerConfig


@dataclass
class MPPIConfig(ControllerConfig):
    """Configuration for MPPI controller."""
    horizon: int = 30                # Planning horizon (timesteps)
    n_samples: int = 100             # Number of trajectory samples
    temperature: float = 1.0         # Softmax temperature (lambda)
    noise_sigma: np.ndarray = field(default_factory=lambda: np.array([0.3, 0.5]))  # [v_noise, psi_dot_noise]

    # Cost weights
    goal_weight: float = 1.0
    terminal_weight: float = 10.0
    control_weight: float = 0.1
    obstacle_weight: float = 100.0
    agent_weight: float = 50.0

    # Safety distances
    obstacle_margin: float = 0.3     # Safety margin around obstacles
    agent_collision_radius: float = 0.4  # Collision radius for other agents


class MPPIController(LocalController):
    """
    Model Predictive Path Integral (MPPI) controller.

    A sampling-based MPC method that:
    1. Samples K control trajectories by adding noise to previous solution
    2. Rolls out dynamics for each trajectory
    3. Computes cost for each trajectory
    4. Weights trajectories by exp(-cost / temperature)
    5. Returns weighted average of first control

    Reference: Williams et al., "Information Theoretic MPC for Model-Based Reinforcement Learning"
    """

    def __init__(
        self,
        config: MPPIConfig,
        dynamics_fn: Optional[Callable] = None,
        cost_fn: Optional[Callable] = None,
    ):
        """
        Args:
            config: MPPI configuration
            dynamics_fn: Optional custom dynamics function (state, control, dt) -> next_state
                        If None, uses default unicycle dynamics
            cost_fn: Optional custom cost function (states, controls, goal, obstacles, agents) -> cost
                    If None, uses default cost function
        """
        super().__init__(config)
        self.config: MPPIConfig = config

        self.dynamics_fn = dynamics_fn if dynamics_fn else self._default_dynamics
        self.cost_fn = cost_fn if cost_fn else self._default_cost

        # Warm start: previous control sequence
        self._prev_controls = np.zeros((config.horizon, 2))

        # Best trajectory from last compute_control call (for visualization)
        self.last_trajectory: Optional[np.ndarray] = None

    def compute_control(
        self,
        state: np.ndarray,
        goal: np.ndarray,
        obstacles: List[np.ndarray],
        other_agents: List[np.ndarray],
    ) -> np.ndarray:
        """
        MPPI algorithm to compute optimal control.

        Args:
            state: Current state [x, y, psi, v, psi_dot]
            goal: Goal position [x, y, psi]
            obstacles: List of obstacles [[x, y, radius], ...]
            other_agents: List of agent states [[x, y, psi, v, psi_dot], ...]

        Returns:
            Optimal control [v, psi_dot]
        """
        K = self.config.n_samples
        H = self.config.horizon

        # Sample control noise
        noise = np.random.randn(K, H, 2) * self.config.noise_sigma

        # Create K candidate control sequences (warm start + noise)
        U_candidates = self._prev_controls[None, :, :] + noise  # [K, H, 2]

        # Clip to control limits
        if self.config.control_limits:
            U_candidates = np.clip(
                U_candidates,
                [self.config.control_limits[0][0], self.config.control_limits[1][0]],
                [self.config.control_limits[0][1], self.config.control_limits[1][1]]
            )

        # Roll out trajectories and compute costs
        costs = np.zeros(K)
        for k in range(K):
            states_k = self._rollout(state, U_candidates[k])
            costs[k] = self.cost_fn(
                states_k, U_candidates[k], goal, obstacles, other_agents, self.config
            )

        # Compute weights (softmax with temperature)
        costs_shifted = costs - np.min(costs)  # Numerical stability
        weights = np.exp(-costs_shifted / self.config.temperature)
        weights = weights / (np.sum(weights) + 1e-10)

        # Weighted average of control sequences
        U_optimal = np.sum(weights[:, None, None] * U_candidates, axis=0)  # [H, 2]

        # Store optimal trajectory for visualization
        self.last_trajectory = self._rollout(state, U_optimal)

        # Warm start for next iteration (shift by 1, repeat last)
        self._prev_controls[:-1] = U_optimal[1:]
        self._prev_controls[-1] = U_optimal[-1]

        # Return first control, clipped
        return self.clip_control(U_optimal[0])

    def _rollout(self, state: np.ndarray, controls: np.ndarray) -> np.ndarray:
        """
        Roll out dynamics given control sequence.

        Args:
            state: Initial state [x, y, psi, v, psi_dot]
            controls: Control sequence [H, 2]

        Returns:
            State trajectory [H+1, 5]
        """
        H = len(controls)
        states = np.zeros((H + 1, len(state)))
        states[0] = state

        for t in range(H):
            states[t + 1] = self.dynamics_fn(states[t], controls[t], self.config.dt)

        return states

    def reset(self):
        """Reset warm start to zeros."""
        self._prev_controls = np.zeros((self.config.horizon, 2))

    # =====================
    # Default dynamics and cost
    # =====================

    @staticmethod
    def _default_dynamics(state: np.ndarray, control: np.ndarray, dt: float) -> np.ndarray:
        """
        Default unicycle dynamics (matches FRODO_Dynamics).

        State: [x, y, psi, v, psi_dot]
        Control: [v, psi_dot]
        """
        x, y, psi, v_prev, psi_dot_prev = state
        v_cmd, psi_dot_cmd = control

        # Simple first-order tracking (instant response)
        v = v_cmd
        psi_dot = psi_dot_cmd

        # Unicycle kinematics
        x_new = x + dt * v * np.cos(psi)
        y_new = y + dt * v * np.sin(psi)
        psi_new = psi + dt * psi_dot

        # Wrap heading to [-pi, pi]
        psi_new = (psi_new + np.pi) % (2 * np.pi) - np.pi

        return np.array([x_new, y_new, psi_new, v, psi_dot])

    @staticmethod
    def _default_cost(
        states: np.ndarray,
        controls: np.ndarray,
        goal: np.ndarray,
        obstacles: List[np.ndarray],
        other_agents: List[np.ndarray],
        config: MPPIConfig,
    ) -> float:
        """
        Default cost function for MPPI.

        Args:
            states: Trajectory states [H+1, 5]
            controls: Control sequence [H, 2]
            goal: Target [x, y, psi]
            obstacles: List of [x, y, radius]
            other_agents: List of [x, y, psi, v, psi_dot]
            config: MPPI configuration

        Returns:
            Total cost (scalar)
        """
        cost = 0.0
        H = len(controls)

        # Goal tracking cost (increasing weight over horizon)
        for t, s in enumerate(states):
            weight = config.goal_weight * (1.0 + t * 0.1)
            cost += weight * np.sum((s[:2] - goal[:2])**2)

        # Terminal cost
        cost += config.terminal_weight * np.sum((states[-1, :2] - goal[:2])**2)

        # Control effort
        cost += config.control_weight * np.sum(controls**2)

        # Obstacle avoidance
        for obs in obstacles:
            if len(obs) < 3:
                continue
            obs_pos = obs[:2]
            obs_radius = obs[2]

            for s in states:
                dist = np.linalg.norm(s[:2] - obs_pos)
                if dist < obs_radius:
                    cost += config.obstacle_weight * 10.0  # Collision
                elif dist < obs_radius + config.obstacle_margin:
                    cost += config.obstacle_weight / (dist - obs_radius + 0.1)

        # Other agent avoidance
        for agent in other_agents:
            if len(agent) < 2:
                continue
            agent_pos = agent[:2]

            for s in states:
                dist = np.linalg.norm(s[:2] - agent_pos)
                if dist < config.agent_collision_radius:
                    cost += config.agent_weight * 10.0  # Collision
                elif dist < config.agent_collision_radius + config.obstacle_margin:
                    cost += config.agent_weight / (dist - config.agent_collision_radius + 0.1)

        return cost


# Convenience function to create MPPI with FRODO dynamics
def create_frodo_mppi(
    dt: float = 0.1,
    horizon: int = 30,
    n_samples: int = 100,
    v_limits: Tuple[float, float] = (-1.0, 1.0),
    psi_dot_limits: Tuple[float, float] = (-2.0, 2.0),
) -> MPPIController:
    """
    Create MPPI controller configured for FRODO robots.

    Args:
        dt: Timestep
        horizon: Planning horizon
        n_samples: Number of samples
        v_limits: Velocity limits (min, max)
        psi_dot_limits: Yaw rate limits (min, max)

    Returns:
        Configured MPPIController
    """
    config = MPPIConfig(
        dt=dt,
        horizon=horizon,
        n_samples=n_samples,
        control_limits=(v_limits, psi_dot_limits),
    )
    return MPPIController(config)
