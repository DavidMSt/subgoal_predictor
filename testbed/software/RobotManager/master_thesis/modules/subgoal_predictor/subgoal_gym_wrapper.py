"""
Gymnasium environment for training a subgoal-prediction RL policy.

The RL agent selects intermediate subgoals; an inner MPPI loop executes
K simulation steps per RL decision, providing temporal abstraction.

Action:  continuous [subgoal_x, subgoal_y]  (Box)
Obs:     [agent_x, agent_y, psi, v, psi_dot,
          goal_x, goal_y, goal_psi,
          neighbors…(padded), obstacles…(padded)]
Reward:  progress toward final goal - collision penalty - time penalty + goal bonus
"""

from __future__ import annotations

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from master_thesis.universal.universal_simulation import FRODO_Universal_Simulation
from master_thesis.universal.universal_agent import FRODOUniversalAgent
from master_thesis.modules.local_control.local_control_module import LocalControlModule
from master_thesis.modules.local_control.mppi_controller import MPPIController, MPPIConfig
from master_thesis.containers.general_containers.agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.local_world_container import LocalWorldContainer


class SubgoalRLEnv(gym.Env):
    """Single-agent subgoal prediction environment with MPPI inner loop."""

    metadata = {"render_modes": []}

    # Observation layout
    _AGENT_DIM = 5   # x, y, psi, v, psi_dot
    _GOAL_DIM = 3    # x, y, psi
    _NEIGHBOR_DIM = 5
    _OBSTACLE_DIM = 3  # x, y, radius

    def __init__(
        self,
        limits: tuple[tuple[float, float], tuple[float, float]] = ((-5, 5), (-5, 5)),
        mppi_steps_per_action: int = 10,
        max_neighbors: int = 4,
        max_obstacles: int = 4,
        max_episode_steps: int = 200,
        goal_threshold: float = 0.3,
        subgoal_range: float = 3.0,
        mppi_horizon: int = 30,
        mppi_n_samples: int = 100,
    ):
        super().__init__()

        self.limits = limits
        self.mppi_steps_per_action = mppi_steps_per_action
        self.max_neighbors = max_neighbors
        self.max_obstacles = max_obstacles
        self.max_episode_steps = max_episode_steps
        self.goal_threshold = goal_threshold
        self.subgoal_range = subgoal_range

        # --- simulation (default OFFLINE pipeline — we drive the agent manually) ---
        self.sim = FRODO_Universal_Simulation(
            Ts=0.1,
            limits=limits,
            run_mode='fast',
        )
        self._configure_logging()

        # --- MPPI controller (created per-reset, needs agent_cont) ---
        self._mppi_horizon = mppi_horizon
        self._mppi_n_samples = mppi_n_samples
        self._lcm: LocalControlModule | None = None

        # --- spaces ---
        self.obs_dim = self._compute_obs_dim()
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(self.obs_dim,), dtype=np.float32,
        )
        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(2,), dtype=np.float32,
        )

        # --- episode state ---
        self._agent: FRODOUniversalAgent | None = None
        self._goal: np.ndarray | None = None
        self._steps: int = 0
        self._prev_dist: float = 0.0

    # ------------------------------------------------------------------
    # Gym API
    # ------------------------------------------------------------------

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.sim.reset_simulation()

        # Spawn one agent and one task
        self.sim.spawn_agents(n=1, log_level='ERROR')
        self.sim.spawn_tasks(n=1)

        agent = list(self.sim.agents.values())[0]
        task = list(self.sim.tasks.values())[0]

        self._agent = agent
        self._goal = np.array([task.container.x, task.container.y, task.container.psi])

        # Build MPPI controller for this agent
        mppi = MPPIController(MPPIConfig(
            dt=self.sim.Ts,
            horizon=self._mppi_horizon,
            n_samples=self._mppi_n_samples,
        ))
        self._lcm = LocalControlModule(
            agent_cont=agent.container,
            controller=mppi,
            logger=agent.logger,
        )
        self._lcm.goal_threshold = self.goal_threshold

        self._steps = 0
        self._prev_dist = self._dist_to_goal()

        obs = self._get_obs()
        return obs, {}

    def step(self, action: np.ndarray):
        assert self._agent is not None and self._lcm is not None

        # Map [-1,1] action to world-frame subgoal relative to agent
        subgoal = self._action_to_subgoal(action)
        self._lcm.set_goal(subgoal, reset_controller=False)

        # Inner MPPI loop: K simulation ticks
        collision = False
        for _ in range(self.mppi_steps_per_action):
            u = self._lcm.step(self._agent.lwr_cont)
            self._agent.input.v = float(u[0])
            self._agent.input.psi_dot = float(u[1])
            self.sim.step()

            if self._check_collision():
                collision = True

        self._steps += 1

        # Reward
        dist = self._dist_to_goal()
        progress = self._prev_dist - dist
        self._prev_dist = dist

        reward = progress * 10.0                     # encourage approach
        if collision:
            reward -= 50.0
        reward -= 0.1                                 # time penalty

        terminated = dist < self.goal_threshold
        if terminated:
            reward += 100.0

        truncated = self._steps >= self.max_episode_steps

        obs = self._get_obs()
        return obs, float(reward), terminated, truncated, {}

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------

    def _compute_obs_dim(self) -> int:
        return (
            self._AGENT_DIM
            + self._GOAL_DIM
            + self.max_neighbors * self._NEIGHBOR_DIM
            + self.max_obstacles * self._OBSTACLE_DIM
        )

    def _get_obs(self) -> np.ndarray:
        assert self._agent is not None and self._goal is not None
        ac = self._agent.container
        lwr = self._agent.lwr_cont

        parts: list[np.ndarray] = []

        # Own agent state
        parts.append(np.array([ac.x, ac.y, ac.psi, ac.state.v, ac.state.psi_dot], dtype=np.float32))

        # Goal
        parts.append(self._goal.astype(np.float32))

        # Neighbors (padded)
        neighbor_obs = np.zeros(self.max_neighbors * self._NEIGHBOR_DIM, dtype=np.float32)
        if lwr is not None and hasattr(lwr, 'neighbors'):
            for i, (_, nc) in enumerate(sorted(lwr.neighbors.items())):
                if i >= self.max_neighbors:
                    break
                off = i * self._NEIGHBOR_DIM
                neighbor_obs[off: off + 5] = [nc.state.x, nc.state.y, nc.state.psi,
                                               nc.state.v, nc.state.psi_dot]
        parts.append(neighbor_obs)

        # Obstacles (padded)
        obstacle_obs = np.zeros(self.max_obstacles * self._OBSTACLE_DIM, dtype=np.float32)
        if lwr is not None and hasattr(lwr, 'obstacles') and lwr.obstacles:
            for i, (_, oc) in enumerate(sorted(lwr.obstacles.items())):
                if i >= self.max_obstacles:
                    break
                off = i * self._OBSTACLE_DIM
                obstacle_obs[off: off + 3] = [oc.x, oc.y, getattr(oc, 'radius', 0.3)]
        parts.append(obstacle_obs)

        return np.concatenate(parts)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _action_to_subgoal(self, action: np.ndarray) -> np.ndarray:
        """Map normalized [-1,1]^2 to world-frame subgoal near the agent."""
        ac = self._agent.container
        dx = float(action[0]) * self.subgoal_range
        dy = float(action[1]) * self.subgoal_range
        return np.array([ac.x + dx, ac.y + dy, 0.0])

    def _dist_to_goal(self) -> float:
        ac = self._agent.container
        return float(np.hypot(ac.x - self._goal[0], ac.y - self._goal[1]))

    def _check_collision(self) -> bool:
        agents = list(self.sim.agents.values())
        if len(agents) < 2:
            return False
        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                d = np.hypot(agents[i].state.x - agents[j].state.x,
                             agents[i].state.y - agents[j].state.y)
                if d < 0.3:
                    return True
        return False

    def _configure_logging(self):
        if hasattr(self.sim, 'logger'):
            self.sim.logger.setLevel('ERROR')
        if hasattr(self.sim.environment, 'logger'):
            self.sim.environment.logger.setLevel('ERROR')
