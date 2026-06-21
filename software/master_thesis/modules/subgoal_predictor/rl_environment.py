import numpy as np
import gymnasium as gym
from gymnasium import spaces
from pathlib import Path

from master_thesis.universal.universal_simulation import FRODO_Universal_Simulation
from master_thesis.scenarios.testbed_importer import load_scenario_yaml
from master_thesis.modules.subgoal_predictor.training_configs.config_loader import BilbolabEnvConfig

_SCENARIOS_DIR = Path(__file__).parent.parent.parent / 'scenarios'


class BilbolabGymWrapper(gym.Env):
    """Bandit-style subgoal-prediction gym wrapper.

    At every reset the RL policy proposes one (x, y, wait_s) subgoal per agent.
    The simulation then runs for up to *max_steps* steps while agents attempt to
    reach their subgoals, and a reward is computed.

    Action space: Box(-inf, inf, shape=(n_agents * 3,))
        Flat vector of [x₀, y₀, w₀, x₁, y₁, w₁, ...] — continuous subgoal positions
        (x, y) in world coordinates and wait time w in seconds per agent.
        Positions are clipped to the scenario limits on decode; wait is clamped to ≥ 0.
    """

    def __init__(self, cfg: BilbolabEnvConfig) -> None:
        super().__init__()

        self.scenario            = load_scenario_yaml((_SCENARIOS_DIR / f'{cfg.scenario}.yaml').read_text())
        self.n_agents            = self.scenario.n_agents_random or len(self.scenario.agents)
        self.max_steps           = cfg.max_steps
        self.agent_log_level     = cfg.agent_log_level
        self.alpha               = cfg.alpha
        self.beta                = cfg.beta
        self.crossing_bonus      = cfg.crossing_bonus
        self.energy_weight       = cfg.energy_weight
        self.diversity_sigma     = cfg.diversity_sigma
        self.diversity_bonus     = cfg.diversity_bonus
        self.ompl_timelimit      = cfg.ompl_timelimit
        self.replan_block_s      = cfg.replan_block_s
        self.skip_penalty        = cfg.skip_penalty
        self.failed_plan_penalty = cfg.failed_plan_penalty
        self.n_gaps              = len(self.scenario.gap_geometry['gaps'])

        self.sim = FRODO_Universal_Simulation(limits=self.scenario.limits, grid_resolution=0.05)
        self.sim.logger.setLevel(cfg.agent_log_level)
        self.sim.environment.logger.setLevel(cfg.agent_log_level)

        self.observation_space = spaces.Dict({
            'agent_psi':      spaces.Box(low=-np.pi, high=np.pi,   shape=(self.n_agents, 1),                        dtype=np.float32),
            'neighbor_rel':   spaces.Box(low=-np.inf, high=np.inf, shape=(self.n_agents, self.n_agents - 1, 2),     dtype=np.float32),
            'goal_rel':       spaces.Box(low=-np.inf, high=np.inf, shape=(self.n_agents, 2),                        dtype=np.float32),
            'neighbor_goals': spaces.Box(low=-np.inf, high=np.inf, shape=(self.n_agents, self.n_agents - 1, 2),     dtype=np.float32),
            'gap_vectors':    spaces.Box(low=-np.inf, high=np.inf, shape=(self.n_agents, self.n_gaps * 2),          dtype=np.float32),
        })
        # Continuous: (x, y, wait_s) per agent, flat
        self.action_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(self.n_agents * 3,), dtype=np.float32,
        )

    # ------------------------------------------------------------------
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)

        self.sim.reset_simulation()
        self.scenario.build(self.sim, log_level=self.agent_log_level)
        self.sim.start_ta()

        import dataclasses
        from master_thesis.modules.motion_planning.ompl_trajectory_planner import OMPLTrajectoryPlanner
        from master_thesis.containers.module_containers.mp_containers.mp_planner_container import AgentMPPlannerConfig as _AgentMPPlannerConfig
        from master_thesis.scenarios.roadmap_utils import load_and_share_roadmap

        _replan_block_ticks = round(self.replan_block_s / self.sim.Ts)
        for _agent in self.sim.agents.values():
            if isinstance(_agent.planner, OMPLTrajectoryPlanner):
                _new_ompl_cfg = dataclasses.replace(
                    _agent.planner.planner_cont.config.planner_config,
                    timelimit=self.ompl_timelimit,
                )
                _agent.planner.planner_cont.config = _AgentMPPlannerConfig(planner_config=_new_ompl_cfg)
            if hasattr(_agent, 'sgm'):
                _agent.sgm.replan_block_ticks = _replan_block_ticks

        if not load_and_share_roadmap(self.sim, self.scenario.name):
            self.sim.logger.warning(f"No PRM* roadmap for '{self.scenario.name}' — build one first.")

        return self._get_obs(), {}

    # ------------------------------------------------------------------
    def step(self, action):
        agents_list  = list(self.sim.agents.values())
        agent_starts = [(float(a.container.x), float(a.container.y)) for a in agents_list]

        predicted_positions = self._assign_subgoals(action)

        # Cache task refs before loop — task may be cleared mid-step on completion.
        task_conts = [agent.assigned_task for agent in agents_list]

        self.sim.start_mp()
        self.sim.start_exe()

        individual_times = [None] * self.n_agents
        terminated = False

        for step in range(self.max_steps):
            self.sim.step()
            for i, (agent, task_cont) in enumerate(zip(agents_list, task_conts)):
                if individual_times[i] is None and task_cont is not None:
                    dx, dy = agent.container.x - task_cont.x, agent.container.y - task_cont.y
                    tol    = task_cont.goal_tolerance_xy
                    if dx*dx + dy*dy < tol*tol:
                        individual_times[i] = step + 1
            if all(t is not None for t in individual_times):
                terminated = True
                break

        makespan  = step + 1
        truncated = not terminated
        obs       = self._get_obs()

        n_failed_plans = sum(a.sgm._failed_plans for a in agents_list)
        reward = self._compute_reward(
            terminated, makespan, individual_times, predicted_positions,
            agent_starts=agent_starts, task_goals=task_conts,
            n_failed_plans=n_failed_plans,
        )

        _y_wall = float(self.scenario.gap_geometry['y_wall'])
        info = {
            'terminated':         terminated,
            'makespan':           makespan,
            'n_failed':           sum(a.sgm._failed_plans     for a in self.sim.agents.values()),
            'n_skipped_subgoals': sum(a.sgm._skipped_subgoals for a in self.sim.agents.values()),
            'n_crossed':          sum(1 for a in self.sim.agents.values()
                                      if a.assigned_task is None or a.container.y <= _y_wall),
            'n_reached_subgoals': sum(max(0, a.sgm._subgoal_idx - a.sgm._skipped_subgoals)
                                      for a in self.sim.agents.values()),
            'plan_wall_time':     sum(a.sgm._total_ompl_wall_time for a in agents_list),
        }
        return obs, reward, terminated, truncated, info

    # ------------------------------------------------------------------
    def _assign_subgoals(self, action: np.ndarray) -> list[tuple[float, float]]:
        """Decode flat (x, y, wait_s) action per agent, inject subgoals, return positions."""
        decoded = action.reshape(self.n_agents, 3)
        lim = self.scenario.limits
        positions = []
        for agent, (sx, sy, wait_s) in zip(self.sim.agents.values(), decoded):
            sx         = float(np.clip(sx, lim[0][0], lim[0][1]))
            sy         = float(np.clip(sy, lim[1][0], lim[1][1]))
            wait_ticks = max(0, int(float(wait_s) / self.sim.Ts))
            agent.sgm.set_subgoals([np.array([sx, sy, 0.0])], wait_ticks=[wait_ticks])
            positions.append((sx, sy))
        return positions

    def _get_obs(self) -> dict:
        return build_subgoal_obs(self.sim, self.scenario.gap_geometry)

    # ------------------------------------------------------------------
    def _compute_reward(
        self,
        terminated: bool,
        makespan: int,
        individual_times: list[int | None],
        predicted_positions: list[tuple[float, float]],
        agent_starts: list[tuple[float, float]],
        task_goals: list,
        n_failed_plans: int,
    ) -> float:
        """Reward signal.

        Terminated: 30-point bonus minus makespan and individual-time fractions.
        Truncated:  gap-aware distance penalty plus crossing bonus and diversity repulsion.

        skip_penalty applies in both branches — closing the bypass exploit where
        the policy predicts a gap-edge subgoal, skips it, and reaches the task
        directly (the 30-point bonus would otherwise dwarf a weak skip penalty).
        """
        n_skipped = sum(a.sgm._skipped_subgoals for a in self.sim.agents.values())

        if terminated:
            makespan_frac   = min(1.0, makespan / self.max_steps)
            mean_indiv_frac = float(np.mean([t / self.max_steps for t in individual_times]))
            return (30.0
                    - 10.0 * makespan_frac
                    - self.alpha * 10.0 * mean_indiv_frac
                    - self.skip_penalty * n_skipped
                    - self.failed_plan_penalty * n_failed_plans)

        # --- truncated ----------------------------------------------------
        gap_geometry = self.scenario.gap_geometry
        y_wall       = float(gap_geometry['y_wall'])
        gaps         = gap_geometry['gaps']

        n_crossed  = 0
        total_dist = 0.0
        for agent in self.sim.agents.values():
            ax, ay = agent.container.x, agent.container.y
            if agent.assigned_task is None:
                n_crossed += 1
                continue
            tx, ty = agent.assigned_task.x, agent.assigned_task.y
            dist   = float(np.hypot(ax - tx, ay - ty))
            if ay > y_wall and gaps:
                dist += min(abs(ax - g['x_center']) for g in gaps)
            elif ay <= y_wall:
                n_crossed += 1
            total_dist += dist

        repulsion = sum(
            float(np.exp(-np.hypot(predicted_positions[i][0] - predicted_positions[j][0],
                                   predicted_positions[i][1] - predicted_positions[j][1]) ** 2
                         / (2 * self.diversity_sigma ** 2)))
            for i in range(len(predicted_positions))
            for j in range(i + 1, len(predicted_positions))
        )

        lim        = self.scenario.limits
        arena_diag = float(np.hypot(lim[0][1] - lim[0][0], lim[1][1] - lim[1][0]))
        raw_extra  = 0.0
        for i, (sx_start, sy_start) in enumerate(agent_starts):
            tc = task_goals[i] if i < len(task_goals) else None
            if tc is None or i >= len(predicted_positions):
                continue
            sx_sg, sy_sg = predicted_positions[i]
            raw_extra += (float(np.hypot(sx_start - sx_sg, sy_start - sy_sg))
                          + float(np.hypot(sx_sg - tc.x,   sy_sg   - tc.y))
                          - float(np.hypot(sx_start - tc.x, sy_start - tc.y)))
        energy_penalty = self.energy_weight * raw_extra / (self.n_agents * arena_diag)

        return (
            - self.beta           * total_dist
            + self.crossing_bonus * n_crossed
            - self.skip_penalty          * n_skipped
            - self.failed_plan_penalty   * n_failed_plans
            - energy_penalty
            - self.diversity_bonus * repulsion
        )


from master_thesis.modules.subgoal_predictor.inference import build_subgoal_obs
