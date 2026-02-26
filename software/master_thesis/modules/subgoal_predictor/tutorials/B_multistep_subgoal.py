import numpy as np
import gymnasium as gym
from gymnasium import spaces

from master_thesis.universal.universal_simulation import FRODO_Universal_Simulation
from master_thesis.containers.general_containers.frodo_agent_container import FRODOAgentContainer
from master_thesis.scenarios.base import ScenarioConfig, AgentSpec, TaskSpec, ObstacleSpec
from master_thesis.scenarios.maze_scenarios import maze_2x2_config


def maze_2x2_3agents_config(
    wall_thickness: float = 0.1,
    agent_class: str = "FRODOOfflineAgent",
) -> ScenarioConfig:
    """2×2 maze with 3 agents (top) and 3 tasks (bottom).

    Reuses the 2×2 obstacle layout; agents and tasks are spread across
    the three accessible columns so they must navigate around walls.
    """
    import math
    base = maze_2x2_config(wall_thickness=wall_thickness, agent_class=agent_class)
    return ScenarioConfig(
        name="maze_2x2_3agents",
        limits=base.limits,
        obstacles=base.obstacles,
        agents=[
            AgentSpec("frodo1", agent_class, start_config=(-0.65, 0.75, 0.0)),
            AgentSpec("frodo2", agent_class, start_config=( 0.0,  0.75, 0.0)),
            AgentSpec("frodo3", agent_class, start_config=( 0.65, 0.75, 0.0)),
        ],
        tasks=[
            TaskSpec("goal1", x=-0.65, y=-0.75),
            TaskSpec("goal2", x= 0.0,  y=-0.75),
            TaskSpec("goal3", x= 0.65, y=-0.75),
        ],
    )


def _grid_shape(
    limits: tuple[tuple[float, float], tuple[float, float]],
    grid_resolution: float = 0.1,
    grid_padding: float = 0.5,
) -> tuple[int, int]:
    """Return (n_rows, n_cols) matching the environment's occupancy grid."""
    x_min = limits[0][0] - grid_padding
    x_max = limits[0][1] + grid_padding
    y_min = limits[1][0] - grid_padding
    y_max = limits[1][1] + grid_padding
    n_x = int(np.ceil((x_max - x_min) / grid_resolution))
    n_y = int(np.ceil((y_max - y_min) / grid_resolution))
    return n_y, n_x


class FrodoGymWrapper(gym.Env):
    """Bandit-style subgoal-prediction gym wrapper.

    At every reset the RL policy proposes one (x, y) subgoal per agent.
    The simulation then runs for up to *max_steps* steps while agents
    attempt to reach their subgoals, and a reward is computed.

    Parameters
    ----------
    scenario:
        A :class:`ScenarioConfig` describing obstacles, agents, and tasks.
        Defaults to the constrained 2×2 maze with 3 agents.
    max_steps:
        Maximum simulation steps before truncation.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        scenario: ScenarioConfig | None = None,
        max_steps: int = 200,
    ) -> None:
        super().__init__()

        self.scenario  = scenario if scenario is not None else maze_2x2_3agents_config()
        self.max_steps = max_steps

        self.n_agents = len(self.scenario.agents)

        lim         = self.scenario.limits
        x_lo, x_hi = lim[0]
        y_lo, y_hi = lim[1]
        agent_lo    = np.array([x_lo, y_lo, -np.pi], dtype=np.float32)
        agent_hi    = np.array([x_hi, y_hi,  np.pi], dtype=np.float32)
        task_lo     = np.array([x_lo, y_lo], dtype=np.float32)
        task_hi     = np.array([x_hi, y_hi], dtype=np.float32)

        n_rows, n_cols = _grid_shape(lim)

        # ----- observation space --------------------------------------------------
        # Agent states: (x, y, psi). Task states: (x, y) — heading irrelevant for goal pos.
        # occupancy_grid: (1, H, W) float32, {0, 1} — channel-first for CNN.
        self.observation_space = spaces.Dict({
            "agent_states": spaces.Box(
                low=np.tile(agent_lo, (self.n_agents, 1)),
                high=np.tile(agent_hi, (self.n_agents, 1)),
                dtype=np.float32,
            ),
            "neighbor_states": spaces.Box(
                low=np.tile(agent_lo, (self.n_agents, self.n_agents - 1, 1)),
                high=np.tile(agent_hi, (self.n_agents, self.n_agents - 1, 1)),
                dtype=np.float32,
            ),
            "task_states": spaces.Box(
                low=np.tile(task_lo, (self.n_tasks, 1)),
                high=np.tile(task_hi, (self.n_tasks, 1)),
                dtype=np.float32,
            ),
            "occupancy_grid": spaces.Box(
                low=0.0, high=1.0,
                shape=(1, n_rows, n_cols),
                dtype=np.float32,
            ),
        })

        # ----- action space -------------------------------------------------------
        # Flat: [x0, y0, x1, y1, ..., x_{N-1}, y_{N-1}]
        self.action_space = spaces.Box(
            low=np.tile(task_lo, self.n_agents),
            high=np.tile(task_hi, self.n_agents),
            dtype=np.float32,
        )

        # ----- simulation (created once, reset each episode) ----------------------
        self.sim = FRODO_Universal_Simulation(limits=lim)
        self._step_count = 0

    # ------------------------------------------------------------------
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)

        self.sim.reset_simulation()
        self.scenario.build(self.sim)
        self._step_count = 0

        obs  = self._get_obs()
        info = {}
        return obs, info

    # ------------------------------------------------------------------
    def step(self, action):
        self.sim.step()
        self._step_count += 1

        obs        = self._get_obs()
        reward     = self._compute_reward(obs, action)
        terminated = self._check_termination(obs)
        truncated  = self._step_count >= self.max_steps
        info       = {}

        return obs, reward, terminated, truncated, info

    # ------------------------------------------------------------------
    def _get_obs(self) -> dict:
        env_cont = self.sim.environment.environment_container

        agent_states = np.array([
            self._agent_to_xy(cont)
            for cont in env_cont.agent_conts.values()
        ], dtype=np.float32)  # (n_agents, 3)

        neighbor_states = self._neighbor_arrays(agent_states)  # (n_agents, n_agents-1, 3)

        task_states = np.array([
            self._task_to_xy(cont)
            for cont in env_cont.task_conts.values()
        ], dtype=np.float32)  # (n_tasks, 2)

        grid = env_cont.occupancy_grid_static.astype(np.float32)[np.newaxis]  # (1, H, W)

        return {
            "agent_states":    agent_states,
            "neighbor_states": neighbor_states,
            "task_states":     task_states,
            "occupancy_grid":  grid,
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _agent_to_xy(cont: FRODOAgentContainer) -> np.ndarray:
        return np.array([cont.x, cont.y, cont.psi], dtype=np.float32)

    @staticmethod
    def _task_to_xy(cont) -> np.ndarray:
        return np.array([cont.x, cont.y], dtype=np.float32)

    @staticmethod
    def _neighbor_arrays(agent_states: np.ndarray) -> np.ndarray:
        """Return (n_agents, n_agents-1, 3) of each agent's neighbor states."""
        n = agent_states.shape[0]
        return np.stack([np.delete(agent_states, i, axis=0) for i in range(n)])

    # ------------------------------------------------------------------
    def _compute_reward(self, obs, action) -> float:
        ...

    def _check_termination(self, obs) -> bool:
        ...

    def render(self):
        ...

    def close(self):
        ...


if __name__ == "__main__":
    env = FrodoGymWrapper()
    obs, info = env.reset()
    print("Observation keys:", list(obs.keys()))
    print("agent_states shape:    ", obs["agent_states"].shape)
    print("neighbor_states shape: ", obs["neighbor_states"].shape)
    print("task_states shape:     ", obs["task_states"].shape)
    print("occupancy_grid shape:  ", obs["occupancy_grid"].shape)
    print("action_space:          ", env.action_space)
