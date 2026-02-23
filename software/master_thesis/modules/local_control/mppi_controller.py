# 3rd party
import numpy as np
from typing import List, Optional
from dataclasses import dataclass, field

# master thesis
from master_thesis.modules.local_control.local_controller import LocalController, ControllerConfig


@dataclass
class MPPIConfig(ControllerConfig):
    """Configuration for MPPI controller."""
    control_limits: tuple[tuple[float, float], tuple[float, float]] | None = ((-1.0, 1.0), (-2.0, 2.0))
    horizon: int = 20                # Planning horizon (timesteps) — 2s at dt=0.1
    n_samples: int = 1000             # Number of trajectory samples
    temperature: float = 1.0         # Softmax temperature (lambda)
    noise_sigma: np.ndarray = field(default_factory=lambda: np.array([0.3, 1.0]))  # [v_noise, psi_dot_noise]

    # Cost weights
    goal_weight: float = 1.0
    heading_weight: float = 5.0      # Penalizes facing away from goal direction
    terminal_weight: float = 10.0
    control_weight: float = 0.1
    obstacle_weight: float = 100.0
    agent_weight: float = 50.0

    # Safety distances
    obstacle_margin: float = 0.15    # Safety margin around obstacles
    agent_collision_radius: float = 0.4  # Collision radius for other agents


class MPPIController(LocalController):
    """
    Model Predictive Path Integral (MPPI) controller.

    A sampling-based MPC method that:
    1. Samples K control trajectories by adding noise to previous solution
    2. Rolls out dynamics for each trajectory (vectorized across all K samples)
    3. Computes cost for each trajectory (vectorized across all K samples)
    4. Weights trajectories by exp(-cost / temperature)
    5. Returns weighted average of first control

    Reference: Williams et al., "Model Predictive Path Integral Control
    using Covariance Variable Importance Sampling"
    """

    def __init__(self, config: MPPIConfig):
        super().__init__(config)
        self.config: MPPIConfig = config

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
        Vectorized MPPI: rolls out all K trajectories as a (K, H+1, 5) tensor.

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
        dt = self.config.dt

        # --- Sample K candidate control sequences (warm start + noise) ---
        noise = np.random.randn(K, H, 2) * self.config.noise_sigma
        U = self._prev_controls[None, :, :] + noise  # (K, H, 2)

        if self.config.control_limits:
            lo = [self.config.control_limits[0][0], self.config.control_limits[1][0]]
            hi = [self.config.control_limits[0][1], self.config.control_limits[1][1]]
            U = np.clip(U, lo, hi)

        # --- Vectorized rollout: (K, H+1, 5) ---
        states = np.zeros((K, H + 1, 5))
        states[:, 0, :] = state  # broadcast initial state

        for t in range(H):
            x   = states[:, t, 0]
            y   = states[:, t, 1]
            psi = states[:, t, 2]
            v       = U[:, t, 0]
            psi_dot = U[:, t, 1]

            states[:, t + 1, 0] = x + dt * v * np.cos(psi)
            states[:, t + 1, 1] = y + dt * v * np.sin(psi)
            psi_new = psi + dt * psi_dot
            states[:, t + 1, 2] = (psi_new + np.pi) % (2 * np.pi) - np.pi
            states[:, t + 1, 3] = v
            states[:, t + 1, 4] = psi_dot

        # --- Vectorized cost across K samples ---
        costs = self._cost(states, U, goal, obstacles, other_agents)

        # --- Compute weights (softmax with temperature) ---
        costs_shifted = costs - np.min(costs)
        weights = np.exp(-costs_shifted / self.config.temperature)
        weights /= np.sum(weights) + 1e-10

        # Weighted average of control sequences
        U_optimal = np.sum(weights[:, None, None] * U, axis=0)  # (H, 2)

        # Store optimal trajectory for visualization (single rollout)
        opt = np.zeros((H + 1, 5))
        opt[0] = state
        for t in range(H):
            v_t = U_optimal[t, 0]
            pd_t = U_optimal[t, 1]
            opt[t + 1, 0] = opt[t, 0] + dt * v_t * np.cos(opt[t, 2])
            opt[t + 1, 1] = opt[t, 1] + dt * v_t * np.sin(opt[t, 2])
            psi_new = opt[t, 2] + dt * pd_t
            opt[t + 1, 2] = (psi_new + np.pi) % (2 * np.pi) - np.pi
            opt[t + 1, 3] = v_t
            opt[t + 1, 4] = pd_t
        self.last_trajectory = opt

        # Warm start for next iteration (shift by 1, repeat last)
        self._prev_controls[:-1] = U_optimal[1:]
        self._prev_controls[-1] = U_optimal[-1]

        return self.clip_control(U_optimal[0])

    def _cost(
        self,
        states: np.ndarray,
        controls: np.ndarray,
        goal: np.ndarray,
        obstacles: List[np.ndarray],
        other_agents: List[np.ndarray],
    ) -> np.ndarray:
        """
        Vectorized cost computation across all K samples.

        Args:
            states: (K, H+1, 5)
            controls: (K, H, 2)
            goal: [x, y, psi]
            obstacles: list of [x, y, radius]
            other_agents: list of [x, y, psi, v, psi_dot]

        Returns:
            costs: (K,)
        """
        cfg = self.config
        K, Hp1 = states.shape[0], states.shape[1]
        H = Hp1 - 1

        # positions: (K, H+1, 2)
        pos = states[:, :, :2]

        # Goal tracking: weighted distance at each timestep
        # weight[t] = goal_weight * (1.0 + t * 0.1), shape (H+1,)
        t_idx = np.arange(Hp1)
        w = cfg.goal_weight * (1.0 + t_idx * 0.1)  # (H+1,)
        diff = pos - goal[:2]                       # (K, H+1, 2)
        sq_dist = np.sum(diff ** 2, axis=2)         # (K, H+1)
        costs = np.sum(w[None, :] * sq_dist, axis=1)  # (K,)

        # Heading-to-goal cost: penalize angle between agent heading and direction to goal
        # Uses atan2(goal - pos) vs agent psi, independent of goal orientation
        psi = states[:, :, 2]                          # (K, H+1)
        dir_to_goal = np.arctan2(diff[:, :, 1] * -1,  # diff = pos - goal, so negate
                                 diff[:, :, 0] * -1)  # (K, H+1)
        ang_err = dir_to_goal - psi
        ang_err = (ang_err + np.pi) % (2 * np.pi) - np.pi  # wrap to [-pi, pi]
        # Scale down near goal so heading cost doesn't fight arrival
        dist = np.sqrt(sq_dist + 1e-6)                # (K, H+1)
        heading_scale = np.minimum(dist, 1.0)          # fades to 0 within 1m of goal
        costs += cfg.heading_weight * np.sum(heading_scale * ang_err ** 2, axis=1)

        # Terminal cost
        costs += cfg.terminal_weight * sq_dist[:, -1]

        # Control effort
        costs += cfg.control_weight * np.sum(controls ** 2, axis=(1, 2))

        # Obstacle avoidance — fully batched over all obstacles
        obs_valid = [o for o in obstacles if len(o) >= 3]
        if obs_valid:
            obs_arr = np.array(obs_valid)                      # (N, 3)
            obs_xy = obs_arr[:, :2]                            # (N, 2)
            obs_r  = obs_arr[:, 2]                             # (N,)
            # pos: (K, H+1, 2) → (K, H+1, 1, 2);  obs_xy → (1, 1, N, 2)
            d = np.sqrt(np.sum((pos[:, :, None, :] - obs_xy[None, None, :, :]) ** 2, axis=3))  # (K, H+1, N)

            collision = d < obs_r[None, None, :]
            margin = (~collision) & (d < obs_r[None, None, :] + cfg.obstacle_margin)

            costs += cfg.obstacle_weight * 10.0 * np.sum(collision, axis=(1, 2))
            safe_d = np.where(margin, d - obs_r[None, None, :] + 0.1, 1.0)
            costs += cfg.obstacle_weight * np.sum(np.where(margin, 1.0 / safe_d, 0.0), axis=(1, 2))

        # Other agent avoidance — fully batched
        ag_valid = [a for a in other_agents if len(a) >= 2]
        if ag_valid:
            ag_xy = np.array([a[:2] for a in ag_valid])        # (M, 2)
            d = np.sqrt(np.sum((pos[:, :, None, :] - ag_xy[None, None, :, :]) ** 2, axis=3))  # (K, H+1, M)

            collision = d < cfg.agent_collision_radius
            margin = (~collision) & (d < cfg.agent_collision_radius + cfg.obstacle_margin)

            costs += cfg.agent_weight * 10.0 * np.sum(collision, axis=(1, 2))
            safe_d = np.where(margin, d - cfg.agent_collision_radius + 0.1, 1.0)
            costs += cfg.agent_weight * np.sum(np.where(margin, 1.0 / safe_d, 0.0), axis=(1, 2))

        return costs

    def reset(self):
        """Reset warm start to zeros."""
        self._prev_controls = np.zeros((self.config.horizon, 2))
