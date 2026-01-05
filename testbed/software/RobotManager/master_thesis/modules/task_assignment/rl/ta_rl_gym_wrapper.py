from master_thesis.universal.universal_simulation import FRODO_universal_Simulation
from master_thesis.universal.universal_agent import FRODOUniversalAgent

from typing import Optional, Type
import gymnasium as gym
import numpy as np

class RLEnvMLP(gym.Env):
    def __init__(self,
                 max_n: int = 10,
                 limits = (((-5,5), (-5, 5))),
                 max_episode_steps = 10000
                 ) -> None:
        
        # x, y, v, psi, psi_dot for each agent
        self.agent_dim = 5
        # x, y, psi
        self.task_dim = 3
        
        self.max_n = max_n
        self.max_episode_steps = max_episode_steps
        self.sim = FRODO_universal_Simulation(Ts = 0.1, limits = limits)

        self.action_space = gym.spaces.Discrete(max_n+1)
        self.obs_dim = self._compute_obs_dim()
        self.observation_space = gym.spaces.Box(
            low = -np.inf,
            high = + np.inf,
            shape= (self.obs_dim,),
            dtype = np.float32
        )
        self.curr_agent_idx = 0

    # TODO: Start with fixed no. of observations when working with MLPs later for GNNs adjust to actual number of the current episode? 
    def _compute_obs_dim(self)-> int:        
        # own agent observation
        dim = self.agent_dim
        # other agents (with padding - have to expect max agents to be used to keep no. of inputs constant for the MLP)
        dim += (self.max_n -1)* self.agent_dim
        # tasks (with padding)
        dim += self.max_n* self.task_dim

        return dim

    # ------------------------------------------------------------------
    # ENVIRONMENT FUNCTIONS (Used by reset and step function)
    # ------------------------------------------------------------------

    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None):
        ...

    def step(self, action):
        ...


    # ------------------------------------------------------------------
    # HELPER FUNCTIONS (Used by reset and step function)
    # ------------------------------------------------------------------

    def _get_obs(self, agent: FRODOUniversalAgent):
        observations = []
        
        lwr_cont = agent.lwr_cont
        assert lwr_cont is not None
        
        # 1. Own agent observations
        own_obs = np.array([lwr_cont.x, lwr_cont.y, lwr_cont.v, lwr_cont.psi, lwr_cont.psi_dot])
        observations.append(own_obs)
        
        # 2. Visible neighbors - sort by ID for consistent ordering
        neighbors_sorted = sorted(lwr_cont.neighbors.items(), key=lambda x: x[0])  # Sort by agent_id
        neighbor_obs = []
        
        for i in range(self.max_n - 1):
            if i < len(neighbors_sorted):
                agent_id, neighbor = neighbors_sorted[i]
                neighbor_obs.extend([
                    neighbor.state.x,
                    neighbor.state.y, 
                    neighbor.state.v,
                    neighbor.state.psi,
                    neighbor.state.psi_dot
                ])
            else:
                # Padding
                neighbor_obs.extend([0.0] * self.agent_dim)
        
        observations.append(np.array(neighbor_obs, dtype=np.float32))
        
        # 3. Visible tasks - sort by task ID for consistent ordering
        tasks_sorted = sorted(lwr_cont.tasks.items(), key=lambda x: x[0])  # Sort by task_id
        task_obs = []
        
        for i in range(self.max_n):
            if i < len(tasks_sorted):
                task_id, task = tasks_sorted[i]
                task_obs.extend([
                    task.goal_config.x,
                    task.goal_config.y,
                    task.goal_config.psi
                ])
            else:
                # Padding
                task_obs.extend([0.0] * self.task_dim)
        
        observations.append(np.array(task_obs, dtype=np.float32))
        
        # Concatenate all parts
        obs = np.concatenate(observations)
        
        assert obs.shape[0] == self.obs_dim, f"Observation size mismatch: {obs.shape[0]} vs {self.obs_dim}"
        
        return obs

    def _get_info(self):
        ...


if __name__ == "__main__":
    ...

