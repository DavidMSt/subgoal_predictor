from master_thesis.universal.universal_simulation import FRODO_Universal_Simulation
from master_thesis.universal.global_plan_agent import FRODOGlobalPlanAgent
from master_thesis.containers.general_containers.local_world_container import LocalWorldContainer
from master_thesis.containers.general_containers.agent_container import FRODOAgentContainer

from typing import Optional, Type
import gymnasium as gym
import numpy as np

class RLEnvMLP(gym.Env):
    def __init__(self,
                 max_n: int = 10,
                 limits = (((-5,5), (-5, 5))),
                 max_episode_steps = 1000
                 ) -> None:

        # x, y, v, psi, psi_dot for each agent
        self.agent_dim = 5
        # x, y, psi
        self.task_dim = 3

        self.max_n = max_n
        self.max_episode_steps = max_episode_steps
        # Use 'fast' mode for non-real-time RL training
        self.sim = FRODO_Universal_Simulation(Ts = 0.1, limits = limits, run_mode='fast')

        # Silence loggers for RL training (only show errors)
        self._configure_logging_for_rl()

        self.action_space = gym.spaces.Discrete(max_n+1)
        self.obs_dim = self._compute_obs_dim()
        self.observation_space = gym.spaces.Box(
            low = -np.inf,
            high = + np.inf,
            shape= (self.obs_dim,),
            dtype = np.float32
        )
        self.curr_agent_idx = 0

    def _configure_logging_for_rl(self):
        """Silence all loggers during RL training (only show ERROR level messages)."""
        # Simulation logger
        if hasattr(self.sim, 'logger'):
            self.sim.logger.setLevel('ERROR')

        # Environment logger
        if hasattr(self.sim.environment, 'logger'):
            self.sim.environment.logger.setLevel('ERROR')

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

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.sim.reset_simulation()
        self._spawn_scenario()
        
        self.agents_list = sorted(self.sim.agents.values(), key=lambda a: a.agent_id)
        assert all(isinstance(agent, FRODOGlobalPlanAgent) for agent in self.agents_list)
        self.curr_agent_idx = 0
        self.agent_actions = {}
        
        # Return observation for FIRST prediction
        obs = self._get_obs(self.agents_list[0])
        return obs, {}


    def step(self, action):
        """
        Two phases:
        1. Decision collection phase: store action, get next agent's obs
        2. Simulation phase: once all decided, run sim and return reward
        """
        # Store current agent's action
        agent_id = self.agents_list[self.curr_agent_idx].agent_id
        self.agent_actions[agent_id] = action
        self.curr_agent_idx += 1
        
        if self.curr_agent_idx >= len(self.agents_list):
            # ALL AGENTS DECIDED - Phase 2: Run simulation
            reward = self._run_simulation_episode()
            terminated = True
            truncated = False
            obs = np.zeros(self.obs_dim, dtype=np.float32)
        else:
            # MORE AGENTS TO GO - Phase 1: Get next observation
            obs = self._get_obs(self.agents_list[self.curr_agent_idx])
            reward = 0.0
            terminated = False
            truncated = False
        
        return obs, reward, terminated, truncated, {}

    # ------------------------------------------------------------------
    # HELPER FUNCTIONS (Used by reset and step function)
    # ------------------------------------------------------------------
    def _spawn_scenario(self):
        n = np.random.randint(2, self.max_n)
        self.sim.spawn_agents(n, log_level='WARNING')
        self.sim.spawn_tasks(n)

    def _get_obs(self, agent: FRODOGlobalPlanAgent):
        observations = []
        
        agent_cont = agent.container
        assert isinstance(agent_cont, FRODOAgentContainer)
        lwr_cont = agent.lwr_cont
        assert isinstance(lwr_cont, LocalWorldContainer)
        
        # 1. Own agent observations
        own_obs = np.array([agent_cont.x, agent_cont.y, agent_cont.v, agent_cont.psi, agent_cont.psi_dot], dtype=np.float32)
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
        return {} # TODO: return debugging info
    
    def _run_simulation_episode(self):
        """
        Apply all task assignments and run simulation until completion.
        Returns reward based on time to completion, collisions, success rate.
        """
        # 1. Apply task assignments
        task_list = sorted(self.sim.tasks.keys())
        
        for agent_id, action in self.agent_actions.items():
            agent = self.sim.agents[agent_id]
            
            if action < len(task_list):
                # Valid task chosen
                task_id = task_list[action]
                task = self.sim.tasks[task_id]

                agent.assigned_task = task.container # assign the container with information to the agent
            else:
                # Invalid action (no task chosen), agent gets no task, will be penalized
                pass

        # Start execution module so agents actually navigate to their tasks
        self.sim.start_exe()

        # 2. Run simulation loop
        completion_times = {}
        collision_count = 0
        
        for sim_step in range(self.max_episode_steps):
            # Step the simulation
            self.sim.step()
            
            # Track task completions
            for agent_id, agent in self.sim.agents.items():
                if agent_id not in completion_times:
                    # Check if agent reached their task
                    if self._agent_reached_task(agent):
                        completion_times[agent_id] = sim_step
            
            # Track collisions (if your sim has collision detection)
            if self._check_collision():
                collision_count += 1
            
            # Early termination if all agents done
            if len(completion_times) == len(self.sim.agents):
                break
        
        # 3. Compute reward
        reward = self._compute_reward(completion_times, collision_count, sim_step)
        
        return reward


    def _agent_reached_task(self, agent):
        """Check if agent has reached their assigned task."""
        if not hasattr(agent, 'assigned_task') or agent.assigned_task is None:
            return False
        
        # Check distance to task goal
        task_cont = agent.assigned_task
        dist = np.linalg.norm([
            agent.container.x - task_cont.x,
            agent.container.y - task_cont.y
        ])
        
        # Threshold for "reached"
        return dist < 0.3  # Adjust based on your robot size


    def _check_collision(self):
        """Check if any collision occurred this timestep."""
        # If your sim has built-in collision detection
        if hasattr(self.sim, 'collision_detected'):
            return self.sim.collision_detected()
        
        # Otherwise, simple pairwise distance check
        agents = list(self.sim.agents.values())
        min_dist = 0.5  # Minimum safe distance
        
        for i in range(len(agents)):
            for j in range(i+1, len(agents)):
                dist = np.linalg.norm([
                    agents[i].state.x - agents[j].state.x,
                    agents[i].state.y - agents[j].state.y
                ])
                if dist < min_dist:
                    return True
        
        return False


    def _compute_reward(self, completion_times, collision_count, final_step):
        """
        Compute reward based on:
        - Success rate (how many agents completed)
        - Time to completion
        - Collisions
        """
        n_agents = len(self.sim.agents)
        n_completed = len(completion_times)
        
        # Failure case: not all agents completed
        if n_completed < n_agents:
            # Heavy penalty for incomplete tasks
            failure_penalty = -1000.0 * (n_agents - n_completed)
            
            # Small reward for agents that did complete
            time_penalty = -sum(completion_times.values()) * 0.1 if completion_times else 0
            
            return failure_penalty + time_penalty
        
        # Success case: all agents completed
        # Reward = negative time (want to minimize) - collision penalty
        max_completion_time = max(completion_times.values())
        
        reward = -max_completion_time  # Want to minimize makespan
        reward -= collision_count * 50.0  # Penalty for collisions
        
        # Bonus for fast completion
        if max_completion_time < 100:
            reward += 100.0
        
        return reward



if __name__ == "__main__":
    ...

