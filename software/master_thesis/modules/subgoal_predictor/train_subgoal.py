import os
import numpy as np
import gymnasium as gym
from tqdm import tqdm
from gymnasium import spaces
import torch
import torch.nn as nn

from master_thesis.universal.universal_simulation import FRODO_Universal_Simulation
from master_thesis.containers.general_containers.frodo_agent_container import FRODOAgentContainer, FRODO_Agent_Config
from master_thesis.scenarios.base import ScenarioConfig, AgentSpec, TaskSpec
from master_thesis.scenarios.testbed_importer import load_scenario_yaml

class subgoal_nn_base(nn.Module):
    def __init__(self, n=3, agent_dim=3, task_dim=2, out_dim=64, n_subgoals=1, grid_shape=(60, 60)) -> None:
        super().__init__()

        self.enc_agent = nn.Linear(in_features=agent_dim, out_features=out_dim)

        self.enc_neighbors = nn.Linear(in_features=(n-1)*agent_dim, out_features=out_dim)

        self.enc_goal = nn.Linear(in_features=task_dim, out_features=out_dim)

        self.enc_goal_neighbors = nn.Linear(in_features=(n-1)*task_dim, out_features=out_dim)

        # flatten size after Conv2d(1, 16, 3, padding=1): 16 * H * W (padding preserves spatial dims)
        grid_flat_dim = 16 * grid_shape[0] * grid_shape[1]
        self.grid_encoder = nn.Sequential(
            nn.Conv2d(in_channels=1, out_channels=16, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Flatten(),
            nn.Linear(in_features=grid_flat_dim, out_features=out_dim)
        )

        self.regression_head = nn.Linear(in_features=5*out_dim, out_features=2*n_subgoals)

    def forward(self,
                agent_input,  # [B,3]
                neighbor_input, # [B, N-1, 3]
                goal_input, # [B, 2]
                neighbor_goal_input, # [B, N-1, 2]
                grid_input # [env_size/ resolution, env_size/ resolution]
                ):
        
        # create embeddings with each encoder
        h_agent = self.enc_agent(agent_input)
        h_neighbors = self.enc_neighbors(neighbor_input)
        h_goal = self.enc_goal(goal_input)
        h_goal_neighbors = self.enc_goal_neighbors(neighbor_goal_input)
        h_grid = self.grid_encoder(grid_input)
        
        # concatenate all 5 encoder outputs
        h = torch.cat(tensors= (h_agent, h_neighbors, h_goal, h_goal_neighbors, h_grid), dim = -1)

        # use regression head for prediction
        subgoals = self.regression_head(h)

        return subgoals


def maze_2x2_3agents_config(
    wall_thickness: float = 0.1,
    agent_class: str = "FRODOOfflineAgent",
) -> ScenarioConfig:
    """2×2 maze with 3 agents (top) and 3 tasks (bottom).

    Reuses the 2×2 obstacle layout; agents and tasks are spread across
    the three accessible columns so they must navigate around walls.
    """
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
            TaskSpec("goal2", x= 0.3,  y=-0.75),
            TaskSpec("goal3", x= 0.65, y=-0.75),
        ],
    )



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
        n_subgoals: int = 3,
        max_steps: int = 200,
        grid_resolution: float = 0.05,
        agent_log_level: str = 'WARNING',
    ) -> None:
        super().__init__()

        _yaml_path = f'{_SUBGOAL_DIR}/../../scenarios/maze_2x2_3agents.yaml'
        self.scenario       = scenario if scenario is not None else load_scenario_yaml(open(_yaml_path).read())
        self.n_subgoals     = n_subgoals
        self.max_steps      = max_steps
        self.agent_log_level = agent_log_level

        self.n_agents = len(self.scenario.agents)

        lim         = self.scenario.limits
        x_lo, x_hi = lim[0]
        y_lo, y_hi = lim[1]
        agent_lo    = np.array([x_lo, y_lo, -np.pi], dtype=np.float32)
        agent_hi    = np.array([x_hi, y_hi,  np.pi], dtype=np.float32)
        # Shrink subgoal action space away from outer walls so that a subgoal at the
        # boundary can never land inside a wall.  Margin = wall half-thickness +
        # robot bounding-circle radius (worst-case corner distance from robot centre).
        _wall_thickness = self.scenario.obstacles[0].width  # outer boundary walls are first
        _robot_cfg = FRODO_Agent_Config()
        _robot_radius = np.hypot(_robot_cfg.length / 2, _robot_cfg.width / 2)
        _clearance = 0.02  # 2 cm safety buffer on top of the geometric minimum
        _sg_margin = float(_wall_thickness / 2 + _robot_radius + _clearance)
        goal_lo     = np.array([x_lo + _sg_margin, y_lo + _sg_margin], dtype=np.float32)
        goal_hi     = np.array([x_hi - _sg_margin, y_hi - _sg_margin], dtype=np.float32)

        # ----- simulation (created once, reset each episode) ----------------------
        self.sim = FRODO_Universal_Simulation(limits=lim, grid_resolution=grid_resolution)

        # Suppress sim-level and environment-level log spam during RL training.
        self.sim.logger.setLevel(agent_log_level)
        self.sim.environment.logger.setLevel(agent_log_level)

        # Grid shape is read directly from the environment — no duplication of
        # internal padding/resolution constants.
        n_rows, n_cols = self.sim.environment.environment_container.occupancy_grid_static.shape
        # TODO: if further resolution increase is needed (e.g. 1 cm → 300×300),
        #       add pooling before Flatten in grid_encoder to keep it tractable.

        # ----- observation space --------------------------------------------------
        # agent_states:    (n_agents, 3)             — own x, y, psi
        # neighbor_states: (n_agents, n_agents-1, 3) — other agents' x, y, psi
        # goal_states:     (n_agents, 2)             — own assigned goal x, y (from TA module)
        # neighbor_goals:  (n_agents, n_agents-1, 2) — neighbors' assigned goals x, y
        # occupancy_grid:  (1, H, W)                 — static obstacle map, channel-first for CNN
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
            "goal_states": spaces.Box(
                low=np.tile(goal_lo, (self.n_agents, 1)),
                high=np.tile(goal_hi, (self.n_agents, 1)),
                dtype=np.float32,
            ),
            "neighbor_goals": spaces.Box(
                low=np.tile(goal_lo, (self.n_agents, self.n_agents - 1, 1)),
                high=np.tile(goal_hi, (self.n_agents, self.n_agents - 1, 1)),
                dtype=np.float32,
            ),
            "occupancy_grid": spaces.Box(
                low=0.0, high=1.0,
                shape=(1, n_rows, n_cols),
                dtype=np.float32,
            ),
        })

        # ----- action space -------------------------------------------------------
        # Flat: [x0_sg0, y0_sg0, x0_sg1, y0_sg1, ..., x_{N-1}_sg_{K-1}, y_{N-1}_sg_{K-1}]
        # Shape: (n_agents * n_subgoals * 2,)
        self.action_space = spaces.Box(
            low=np.tile(goal_lo, self.n_agents * self.n_subgoals),
            high=np.tile(goal_hi, self.n_agents * self.n_subgoals),
            dtype=np.float32,
        )

    # ------------------------------------------------------------------
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)

        self.sim.reset_simulation()
        self.scenario.build(self.sim, log_level=self.agent_log_level)
        self.sim.start_ta()

        obs  = self._get_obs()
        info = {}
        return obs, info

    # ------------------------------------------------------------------
    def step(self, action):

        self._assign_subgoals(action)
        self.sim.start_mp()
        self.sim.start_exe()

        individual_times = [None] * self.n_agents  # step at which each agent reached its goal
        terminated = False

        # Cache task refs before the loop — SubgoalManager._complete_task() clears
        # agent.assigned_task mid-step, which would cause us to miss completion events.
        agents_list = list(self.sim.agents.values())
        task_conts  = [agent.assigned_task for agent in agents_list]

        for step in range(self.max_steps):
            self.sim.step()

            # track per-agent arrivals
            for i, (agent, task_cont) in enumerate(zip(agents_list, task_conts)):
                if individual_times[i] is None and task_cont is not None:
                    dx  = agent.container.x - task_cont.x
                    dy  = agent.container.y - task_cont.y
                    tol = task_cont.goal_tolerance_xy
                    if dx*dx + dy*dy < tol*tol:
                        individual_times[i] = step + 1

            if all(t is not None for t in individual_times):
                terminated = True
                break

        makespan  = step + 1
        truncated = not terminated
        obs       = self._get_obs()
        reward    = self._compute_reward(terminated, makespan, individual_times)
        info      = {
            'terminated':        terminated,
            'makespan':          makespan,
            'n_failed':          sum(agent.sgm._failed_plans      for agent in self.sim.agents.values()),
            'n_skipped_subgoals': sum(agent.sgm._skipped_subgoals for agent in self.sim.agents.values()),
        }

        return obs, reward, terminated, truncated, info
            
    # ------------------------------------------------------------------
    def _assign_subgoals(self, action: np.ndarray) -> None:
        """Distribute RL-predicted subgoals to each agent's SubgoalManager.

        Reshapes the flat action vector into (n_agents, n_subgoals, 2) and
        passes each agent's sequence to its sgm.set_subgoals().  Heading is
        set to 0.0 since the planner ignores it for intermediate waypoints.
        """
        subgoals = action.reshape(self.n_agents, self.n_subgoals, 2)
        for agent, agent_subgoals in zip(self.sim.agents.values(), subgoals):
            seq = [np.array([sg[0], sg[1], 0.0], dtype=np.float32) for sg in agent_subgoals]
            agent.sgm.set_subgoals(seq)

    # ------------------------------------------------------------------
    def _get_obs(self) -> dict:
        env_cont = self.sim.environment.environment_container

        # agent-related observations
        agent_states = np.array([
            self._agent_to_xy(cont)
            for cont in env_cont.agent_conts.values()
        ], dtype=np.float32)  # (n_agents, 3)

        neighbor_states = self._neighbor_arrays(agent_states)  # (n_agents, n_agents-1, 3)

        # goal-related observations — keyed by agent to match agent_states row order
        goal_states = np.array([
            self._goal_to_xy(agent.assigned_task) if agent.assigned_task is not None
            else np.zeros(2, dtype=np.float32)
            for agent in self.sim.agents.values()
        ], dtype=np.float32)  # (n_agents, 2)

        neighbor_goals = self._neighbor_arrays(goal_states)  # (n_agents, n_agents-1, 2)

        grid = env_cont.occupancy_grid_static.astype(np.float32)[np.newaxis]  # (1, H, W)

        return {
            "agent_states":    agent_states,
            "neighbor_states": neighbor_states,
            "goal_states":     goal_states,
            "neighbor_goals":  neighbor_goals,
            "occupancy_grid":  grid,
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _agent_to_xy(cont: FRODOAgentContainer) -> np.ndarray:
        return np.array([cont.x, cont.y, cont.psi], dtype=np.float32)

    @staticmethod
    def _goal_to_xy(cont) -> np.ndarray:
        return np.array([cont.x, cont.y], dtype=np.float32)

    @staticmethod
    def _neighbor_arrays(agent_states: np.ndarray) -> np.ndarray:
        """Return (n_agents, n_agents-1, 3) of each agent's neighbor states."""
        n = agent_states.shape[0]
        return np.stack([np.delete(agent_states, i, axis=0) for i in range(n)])

    # ------------------------------------------------------------------
    def _compute_reward(
        self,
        terminated: bool,
        makespan: int,
        individual_times: list[int | None],
        alpha: float = 0.3,
        beta: float = 1.0,
        gamma: float = 10.0,
    ) -> float:
        """Compute reward signal.

        Terminated: combine makespan (team objective) with sum of individual
        completion times (per-agent progress) and a failed-plan penalty.
        Truncated: distance fallback — sum of final distances to goals,
        ensuring non-zero gradient signal early in training, plus failed-plan penalty.

        Parameters
        ----------
        alpha: weight of individual completion times relative to makespan
        beta:  scale of distance fallback when no agent finishes
        gamma: penalty per OMPL planning failure (discourages wall-embedded subgoals)
        """
        n_failed = sum(
            agent.sgm._failed_plans
            for agent in self.sim.agents.values()
        )

        if terminated:
            return -makespan - alpha * sum(individual_times) - gamma * n_failed

        # distance fallback for agents that did not reach their goal
        # (completed agents have assigned_task cleared — their distance contribution is 0)
        total_dist = sum(
            np.hypot(agent.container.x - agent.assigned_task.x,
                     agent.container.y - agent.assigned_task.y)
            for agent in self.sim.agents.values()
            if agent.assigned_task is not None
        )
        return -beta * total_dist - gamma * n_failed

    def render(self):
        ...

    def close(self):
        ...


_SUBGOAL_DIR = '/Users/davidstoll/Documents/TU/bilbolab_thesis/software/master_thesis/modules/subgoal_predictor'

def train(n_updates, batch_size, n_subgoals = 3,
          log_dir: str = f'{_SUBGOAL_DIR}/runs/subgoal_B',
          checkpoint_path: str | None = f'{_SUBGOAL_DIR}/checkpoints/subgoal_B.pt',
          save_every: int = 50):
    from torch.utils.tensorboard import SummaryWriter

    # load environment — ERROR level suppresses expected OMPL/SubgoalManager warnings
    scenario = load_scenario_yaml(open(f'{_SUBGOAL_DIR}/../../scenarios/maze_2x2_3agents.yaml').read())
    env = FrodoGymWrapper(scenario=scenario, agent_log_level='ERROR', n_subgoals=n_subgoals)

    # get the grid shape (discretization of env to determine free workspace)
    grid_shape = env.sim.environment.environment_container.occupancy_grid_static.shape

    # Create policy instance (NN that predicts our subgoals)
    policy = subgoal_nn_base(n=env.n_agents, n_subgoals=env.n_subgoals, grid_shape=grid_shape)

    # Learnable Parameter (Used only during training) to enable/ increase exploration during RL
    log_std = torch.nn.Parameter(torch.zeros(env.n_agents, env.n_subgoals * 2))

    # Selected optimizer to perform optimization step, uses policy parameters + learnable parameter (latter will converge to zero during (successful) training)
    optimizer = torch.optim.Adam([*policy.parameters(), log_std])

    # Resume from checkpoint if provided
    start_update = 0
    if checkpoint_path and os.path.exists(checkpoint_path):
        ckpt = torch.load(checkpoint_path)
        policy.load_state_dict(ckpt['policy'])
        log_std.data = ckpt['log_std']
        optimizer.load_state_dict(ckpt['optimizer'])
        start_update = ckpt['update'] + 1
        print(f"Resumed from '{checkpoint_path}' at update {start_update}")

    # TensorBoard — append to existing run when resuming
    writer = SummaryWriter(log_dir)

    print(f"Training: updates {start_update}–{start_update + n_updates - 1} * {batch_size} episodes | logdir={log_dir}")

    update_pbar = tqdm(range(start_update, start_update + n_updates), desc='Updates')

    try:
        for update in update_pbar:
            raw_rewards, log_probs = [], []
            ep_terminated, ep_makespans, ep_failed, ep_skipped = [], [], [], []

            for episode in tqdm(range(batch_size), desc='Episodes', leave=False):
                obs, _ = env.reset()

                obs_t = {k: torch.as_tensor(v, dtype=torch.float32) for k, v in obs.items()}
                n     = env.n_agents

                # Use policy prediction as mean, add noise to facilitate exploration
                mean = policy(
                    obs_t["agent_states"],                                        # (N, 3)
                    obs_t["neighbor_states"].flatten(-2),                         # (N, (N-1)*3)
                    obs_t["goal_states"],                                         # (N, 2)
                    obs_t["neighbor_goals"].flatten(-2),                          # (N, (N-1)*2)
                    obs_t["occupancy_grid"].unsqueeze(0).expand(n, -1, -1, -1),  # (N, 1, H, W)
                )  # → (N, n_subgoals*2)
                dist = torch.distributions.Normal(mean, log_std.exp())

                action   = dist.sample()
                log_prob = dist.log_prob(action).sum()

                _, reward, terminated, truncated, info = env.step(action.flatten().numpy())

                raw_rewards.append(reward)
                log_probs.append(log_prob)
                ep_terminated.append(info['terminated'])
                ep_makespans.append(info['makespan'])
                ep_failed.append(info['n_failed'])
                ep_skipped.append(info['n_skipped_subgoals'])

            # REINFORCE update
            rewards_t  = torch.tensor(raw_rewards)
            normalized = (rewards_t - rewards_t.mean()) / (rewards_t.std() + 1e-8)
            loss       = -(torch.stack(log_probs) * normalized).mean()

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            mean_reward   = float(rewards_t.mean())
            std_reward    = float(rewards_t.std())
            n_done        = sum(ep_terminated)
            frac_done     = n_done / batch_size
            done_spans    = [m for m, t in zip(ep_makespans, ep_terminated) if t]
            mean_makespan = float(np.mean(done_spans)) if done_spans else float(env.max_steps)
            mean_failed   = float(np.mean(ep_failed))
            mean_skipped  = float(np.mean(ep_skipped))

            writer.add_scalar('train/loss',                 float(loss),   update)
            writer.add_scalar('train/mean_reward',          mean_reward,   update)
            writer.add_scalar('train/std_reward',           std_reward,    update)
            writer.add_scalar('train/frac_terminated',      frac_done,     update)
            writer.add_scalar('train/mean_makespan',        mean_makespan, update)
            writer.add_scalar('train/mean_failed_plans',    mean_failed,   update)
            writer.add_scalar('train/mean_skipped_subgoals', mean_skipped, update)
            writer.flush()

            update_pbar.set_postfix({
                'loss':   f'{float(loss):+.3f}',
                'rew':    f'{mean_reward:+.1f}',
                'done':   f'{n_done}/{batch_size}',
                'span':   f'{mean_makespan:.0f}',
                'failed': f'{mean_failed:.1f}',
            })

            if checkpoint_path and (update + 1) % save_every == 0:
                os.makedirs(os.path.dirname(checkpoint_path) or '.', exist_ok=True)
                torch.save({
                    'update':    update,
                    'policy':    policy.state_dict(),
                    'log_std':   log_std.data,
                    'optimizer': optimizer.state_dict(),
                }, checkpoint_path)

    except KeyboardInterrupt:
        tqdm.write("Interrupted — saving checkpoint...")
        if checkpoint_path:
            os.makedirs(os.path.dirname(checkpoint_path) or '.', exist_ok=True)
            torch.save({
                'update':    update,
                'policy':    policy.state_dict(),
                'log_std':   log_std.data,
                'optimizer': optimizer.state_dict(),
            }, checkpoint_path)
            tqdm.write(f"Saved to '{checkpoint_path}' at update {update}")

    writer.close()

if __name__ == "__main__":
    # Fresh run and resume both use the same call — checkpoint presence is auto-detected.
    # Start with n_subgoals=1 (6-dim actions) — easier for REINFORCE to learn.
    # Once converged, transfer encoder weights to n_subgoals=3 via finetune_from_checkpoint().
    train(n_updates=500, batch_size=32, n_subgoals=1,
          log_dir=f'{_SUBGOAL_DIR}/runs/subgoal_B_sg1',
          checkpoint_path=f'{_SUBGOAL_DIR}/checkpoints/subgoal_B_sg1.pt')
