# 3rd party
import numpy as np
from scipy.optimize import minimize
from typing import List, Callable, Optional, Tuple
from dataclasses import dataclass, field

# master thesis
from master_thesis.modules.local_control.local_controller import LocalController, ControllerConfig


@dataclass
class MPCConfig(ControllerConfig):
    """Configuration for MPC controller."""
    horizon: int = 20                # Planning horizon (timesteps)
    max_iter: int = 50               # Maximum optimization iterations
    tolerance: float = 1e-4          # Optimization tolerance

    # Cost weights
    goal_weight: float = 1.0
    terminal_weight: float = 10.0
    control_weight: float = 0.1
    control_rate_weight: float = 0.05  # Penalty on control changes
    obstacle_weight: float = 100.0
    agent_weight: float = 50.0

    # Safety distances
    obstacle_margin: float = 0.3     # Safety margin around obstacles
    agent_collision_radius: float = 0.4  # Collision radius for other agents

    # Optimization method ('SLSQP', 'L-BFGS-B', 'trust-constr')
    method: str = 'SLSQP'


class MPCController(LocalController):
    """
    Model Predictive Control (MPC) controller using optimization.

    Unlike MPPI which samples trajectories and weights them probabilistically,
    MPC directly solves an optimization problem to find the optimal control sequence.

    This implementation uses scipy.optimize for the underlying optimization,
    making it suitable for nonlinear dynamics and cost functions.

    Key differences from MPPI:
    - Deterministic optimization vs stochastic sampling
    - Generally more computationally efficient for shorter horizons
    - Can incorporate hard constraints via the optimizer
    - More sensitive to local minima
    """

    def __init__(
        self,
        config: MPCConfig,
        dynamics_fn: Optional[Callable] = None,
        cost_fn: Optional[Callable] = None,
    ):
        """
        Args:
            config: MPC configuration
            dynamics_fn: Optional custom dynamics function (state, control, dt) -> next_state
                        If None, uses default unicycle dynamics
            cost_fn: Optional custom cost function (states, controls, goal, obstacles, agents, config) -> cost
                    If None, uses default cost function
        """
        super().__init__(config)
        self.config: MPCConfig = config

        self.dynamics_fn = dynamics_fn if dynamics_fn else self._default_dynamics
        self.cost_fn = cost_fn if cost_fn else self._default_cost

        # Warm start: previous control sequence
        self._prev_controls = np.zeros((config.horizon, 2))

        # Cache for current optimization context
        self._current_state = None
        self._current_goal = None
        self._current_obstacles = None
        self._current_agents = None

    def compute_control(
        self,
        state: np.ndarray,
        goal: np.ndarray,
        obstacles: List[np.ndarray],
        other_agents: List[np.ndarray],
    ) -> np.ndarray:
        """
        MPC optimization to compute optimal control.

        Args:
            state: Current state [x, y, psi, v, psi_dot]
            goal: Goal position [x, y, psi]
            obstacles: List of obstacles [[x, y, radius], ...]
            other_agents: List of agent states [[x, y, psi, v, psi_dot], ...]

        Returns:
            Optimal control [v, psi_dot]
        """
        H = self.config.horizon

        # Store context for objective function
        self._current_state = state
        self._current_goal = goal
        self._current_obstacles = obstacles
        self._current_agents = other_agents

        # Initial guess from warm start
        u0 = self._prev_controls.flatten()

        # Set up bounds for optimization
        bounds = self._get_bounds(H)

        # Run optimization
        result = minimize(
            fun=self._objective,
            x0=u0,
            method=self.config.method,
            bounds=bounds,
            options={
                'maxiter': self.config.max_iter,
                'ftol': self.config.tolerance,
                'disp': False,
            }
        )

        # Extract optimal control sequence
        U_optimal = result.x.reshape(H, 2)

        # Warm start for next iteration (shift by 1, repeat last)
        self._prev_controls[:-1] = U_optimal[1:]
        self._prev_controls[-1] = U_optimal[-1]

        # Return first control, clipped
        return self.clip_control(U_optimal[0])

    def _objective(self, u_flat: np.ndarray) -> float:
        """
        Objective function for optimization.

        Args:
            u_flat: Flattened control sequence [H*2]

        Returns:
            Total cost (scalar)
        """
        H = self.config.horizon
        controls = u_flat.reshape(H, 2)

        # Roll out trajectory
        states = self._rollout(self._current_state, controls)

        # Compute cost
        return self.cost_fn(
            states, controls,
            self._current_goal,
            self._current_obstacles,
            self._current_agents,
            self.config
        )

    def _get_bounds(self, H: int) -> List[Tuple[float, float]]:
        """Get bounds for optimization variables."""
        if self.config.control_limits is None:
            return None

        v_limits, psi_dot_limits = self.config.control_limits
        bounds = []
        for _ in range(H):
            bounds.append(v_limits)      # v bounds
            bounds.append(psi_dot_limits)  # psi_dot bounds
        return bounds

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
        config: MPCConfig,
    ) -> float:
        """
        Default cost function for MPC.

        Uses smooth penalty functions for obstacle avoidance to enable
        gradient-based optimization.

        Args:
            states: Trajectory states [H+1, 5]
            controls: Control sequence [H, 2]
            goal: Target [x, y, psi]
            obstacles: List of [x, y, radius]
            other_agents: List of [x, y, psi, v, psi_dot]
            config: MPC configuration

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

        # Control rate penalty (smoothness)
        for t in range(1, H):
            du = controls[t] - controls[t-1]
            cost += config.control_rate_weight * np.sum(du**2)

        # Obstacle avoidance (smooth barrier function)
        for obs in obstacles:
            if len(obs) < 3:
                continue
            obs_pos = obs[:2]
            obs_radius = obs[2]
            safe_dist = obs_radius + config.obstacle_margin

            for s in states:
                dist = np.linalg.norm(s[:2] - obs_pos)
                # Smooth exponential barrier
                if dist < safe_dist * 2:
                    cost += config.obstacle_weight * np.exp(-2 * (dist - safe_dist) / safe_dist)

        # Other agent avoidance (smooth barrier function)
        for agent in other_agents:
            if len(agent) < 2:
                continue
            agent_pos = agent[:2]
            safe_dist = config.agent_collision_radius + config.obstacle_margin

            for s in states:
                dist = np.linalg.norm(s[:2] - agent_pos)
                # Smooth exponential barrier
                if dist < safe_dist * 2:
                    cost += config.agent_weight * np.exp(-2 * (dist - safe_dist) / safe_dist)

        return cost


class MPCControllerCasadi(LocalController):
    """
    MPC controller using CasADi for efficient nonlinear optimization.

    This provides faster optimization than scipy for real-time MPC,
    but requires CasADi to be installed.

    Falls back to scipy-based MPC if CasADi is not available.
    """

    def __init__(
        self,
        config: MPCConfig,
        dynamics_fn: Optional[Callable] = None,
        cost_fn: Optional[Callable] = None,
    ):
        super().__init__(config)
        self.config: MPCConfig = config

        try:
            import casadi as ca
            self._use_casadi = True
            self._setup_casadi_solver()
        except ImportError:
            print("CasADi not available, falling back to scipy MPC")
            self._use_casadi = False
            self._fallback = MPCController(config, dynamics_fn, cost_fn)

        self._prev_controls = np.zeros((config.horizon, 2))

    def _setup_casadi_solver(self):
        """Set up CasADi optimization problem."""
        import casadi as ca

        H = self.config.horizon
        dt = self.config.dt

        # State and control dimensions
        nx = 5  # [x, y, psi, v, psi_dot]
        nu = 2  # [v, psi_dot]

        # Decision variables: controls over horizon
        U = ca.MX.sym('U', nu, H)

        # Parameters: initial state, goal
        x0 = ca.MX.sym('x0', nx)
        goal = ca.MX.sym('goal', 3)

        # Build trajectory symbolically
        X = [x0]
        for t in range(H):
            x_curr = X[-1]
            u_curr = U[:, t]

            # Unicycle dynamics
            x_next = ca.vertcat(
                x_curr[0] + dt * u_curr[0] * ca.cos(x_curr[2]),
                x_curr[1] + dt * u_curr[0] * ca.sin(x_curr[2]),
                x_curr[2] + dt * u_curr[1],
                u_curr[0],
                u_curr[1]
            )
            X.append(x_next)

        # Cost function
        cost = 0
        for t, x in enumerate(X):
            weight = self.config.goal_weight * (1.0 + t * 0.1)
            cost += weight * ((x[0] - goal[0])**2 + (x[1] - goal[1])**2)

        # Terminal cost
        cost += self.config.terminal_weight * ((X[-1][0] - goal[0])**2 + (X[-1][1] - goal[1])**2)

        # Control effort
        cost += self.config.control_weight * ca.sumsqr(U)

        # Control rate
        for t in range(1, H):
            cost += self.config.control_rate_weight * ca.sumsqr(U[:, t] - U[:, t-1])

        # Set up NLP
        nlp = {
            'x': ca.reshape(U, -1, 1),
            'f': cost,
            'p': ca.vertcat(x0, goal)
        }

        # Solver options
        opts = {
            'ipopt.print_level': 0,
            'ipopt.max_iter': self.config.max_iter,
            'ipopt.tol': self.config.tolerance,
            'print_time': False,
        }

        self._solver = ca.nlpsol('solver', 'ipopt', nlp, opts)
        self._H = H
        self._nu = nu

        # Bounds
        if self.config.control_limits:
            v_lim, psi_lim = self.config.control_limits
            self._lbx = np.tile([v_lim[0], psi_lim[0]], H)
            self._ubx = np.tile([v_lim[1], psi_lim[1]], H)
        else:
            self._lbx = -np.inf * np.ones(H * nu)
            self._ubx = np.inf * np.ones(H * nu)

    def compute_control(
        self,
        state: np.ndarray,
        goal: np.ndarray,
        obstacles: List[np.ndarray],
        other_agents: List[np.ndarray],
    ) -> np.ndarray:
        """Compute optimal control using CasADi or fallback."""
        if not self._use_casadi:
            return self._fallback.compute_control(state, goal, obstacles, other_agents)

        # Solve NLP
        p = np.concatenate([state, goal[:3]])
        x0 = self._prev_controls.flatten()

        sol = self._solver(
            x0=x0,
            p=p,
            lbx=self._lbx,
            ubx=self._ubx
        )

        U_optimal = np.array(sol['x']).reshape(self._H, self._nu)

        # Warm start
        self._prev_controls[:-1] = U_optimal[1:]
        self._prev_controls[-1] = U_optimal[-1]

        return self.clip_control(U_optimal[0])

    def reset(self):
        """Reset warm start."""
        self._prev_controls = np.zeros((self.config.horizon, 2))
        if not self._use_casadi:
            self._fallback.reset()


# Convenience function to create MPC with FRODO dynamics
def create_frodo_mpc(
    dt: float = 0.1,
    horizon: int = 20,
    v_limits: Tuple[float, float] = (-1.0, 1.0),
    psi_dot_limits: Tuple[float, float] = (-2.0, 2.0),
    use_casadi: bool = False,
) -> LocalController:
    """
    Create MPC controller configured for FRODO robots.

    Args:
        dt: Timestep
        horizon: Planning horizon
        v_limits: Velocity limits (min, max)
        psi_dot_limits: Yaw rate limits (min, max)
        use_casadi: Use CasADi solver (faster, requires CasADi installed)

    Returns:
        Configured MPC controller
    """
    config = MPCConfig(
        dt=dt,
        horizon=horizon,
        control_limits=(v_limits, psi_dot_limits),
    )

    if use_casadi:
        return MPCControllerCasadi(config)
    return MPCController(config)
