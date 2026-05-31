import numpy as np
import gymnasium as gym
from gymnasium import spaces
from pathlib import Path

from master_thesis.universal.universal_simulation import FRODO_Universal_Simulation
from master_thesis.containers.general_containers.frodo_agent_container import FRODOAgentContainer, FRODO_Agent_Config

from master_thesis.scenarios.testbed_importer import load_scenario_yaml

# Path where all scenarios are
_SCENARIOS_DIR = Path(__file__).parent.parent.parent / 'scenarios'

class BilbolabGymWrapper(gym.Env):
    """Bandit-style subgoal-prediction gym wrapper.

    At every reset the RL policy proposes one (x, y) subgoal per agent.
    The simulation then runs for up to *max_steps* steps while agents
    attempt to reach their subgoals, and a reward is computed.

    Parameters
    ----------
    scenario:
        Name of a YAML file in ``scenarios/`` without the extension,
        e.g. ``"rl_5n_random_2x2"``.  The agent count is read from
        ``agent_spawn_region.n`` in that file.
    max_steps:
        Maximum simulation steps before truncation.
    """

    def __init__(
        self,
        scenario: str,
        n_subgoals: int = 1,
        max_steps: int = 200,
        grid_resolution: float = 0.05,
        grid_stride: float = 0.5,
        agent_log_level: str = 'WARNING',
        diversity_sigma: float = 0.35,
        diversity_bonus: float = 1.5,
        ompl_timelimit: float = 10.0,
        wait_times: list | None = None,
        wait_mode: str = 'discrete',
        skip_penalty: float = 4.0,
        failed_plan_penalty: float = 0.0,
    ) -> None:
        super().__init__()

        self.scenario        = load_scenario_yaml((_SCENARIOS_DIR / f'{scenario}.yaml').read_text())
        self.n_agents        = self.scenario.n_agents_random or len(self.scenario.agents)
        self.n_subgoals      = n_subgoals
        self.max_steps       = max_steps
        self.grid_stride     = grid_stride
        self.agent_log_level = agent_log_level
        self.diversity_sigma = diversity_sigma
        self.diversity_bonus = diversity_bonus
        self.ompl_timelimit  = ompl_timelimit
        self.wait_times      = wait_times if wait_times else None # for discrete wait times possible classes need to be provided
        self.wait_mode            = wait_mode
        self.skip_penalty         = skip_penalty
        self.failed_plan_penalty  = failed_plan_penalty

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

        # Free-workspace positions — built in reset() after obstacles are placed.
        self._free_positions = None

        # PRM* roadmap — loaded once per process via the shared cache in
        # master_thesis.scenarios.roadmap_utils; no instance-level cache needed.

        self.n_gaps = len(self.scenario.gap_geometry['gaps'])

        # ----- observation space --------------------------------------------------
        # agent_psi:      (n_agents, 1)              — own heading ψ
        # neighbor_rel:   (n_agents, n_agents-1, 2)  — sensor (Δx, Δy) per neighbor
        # goal_rel:       (n_agents, 2)              — relative (Δx, Δy) to own task
        # gap_vectors:    (n_agents, n_gaps*2)       — (Δx, Δy) to each gap center
        # neighbor_goals: (n_agents, n_agents-1, 2)  — DGNN-GA goal (Δx, Δy) per neighbor
        # See obs_design_notes.md for rationale.
        self.observation_space = spaces.Dict({
            "agent_psi": spaces.Box(
                low=-np.pi, high=np.pi,
                shape=(self.n_agents, 1),
                dtype=np.float32,
            ),
            "neighbor_rel": spaces.Box(
                low=-np.inf, high=np.inf,
                shape=(self.n_agents, self.n_agents - 1, 2),
                dtype=np.float32,
            ),
            "goal_rel": spaces.Box(
                low=-np.inf, high=np.inf,
                shape=(self.n_agents, 2),
                dtype=np.float32,
            ),
            "neighbor_goals": spaces.Box(
                low=-np.inf, high=np.inf,
                shape=(self.n_agents, self.n_agents - 1, 2),
                dtype=np.float32,
            ),
            "gap_vectors": spaces.Box(
                low=-np.inf, high=np.inf,
                shape=(self.n_agents, self.n_gaps * 2),
                dtype=np.float32,
            ),
        })

        # ----- action space -------------------------------------------------------
        # Flat: [pos_0, wait_0, pos_1, wait_1, ..., pos_{N-1}, wait_{N-1}]
        # N_positions is determined after first reset(); placeholder set here.
        self.action_space = spaces.MultiDiscrete(
            np.array([[1, len(self.wait_times)]] * (self.n_agents * self.n_subgoals)).flatten()
            if self.n_subgoals > 0 else np.array([1])
        )

    # ------------------------------------------------------------------
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)

        self.sim.reset_simulation()
        self.scenario.build(self.sim, log_level=self.agent_log_level)
        self.sim.start_ta()

        # Patch OMPL timelimit on each agent's lazily-created planner.
        # Must happen after build() (agents exist) and before start_mp() in step()
        # (planner created on first plan() call).
        import dataclasses
        from master_thesis.modules.motion_planning.ompl_trajectory_planner import OMPLTrajectoryPlanner
        from master_thesis.containers.module_containers.mp_containers.mp_planner_container import AgentMPPlannerConfig as _AgentMPPlannerConfig
        from master_thesis.scenarios.roadmap_utils import load_and_share_roadmap

        # Patch OMPL timelimit on each agent's planner.
        for _agent in self.sim.agents.values():
            if isinstance(_agent.planner, OMPLTrajectoryPlanner):
                _new_ompl_cfg = dataclasses.replace(
                    _agent.planner.planner_cont.config.planner_config,
                    timelimit=self.ompl_timelimit,
                )
                _agent.planner.planner_cont.config = _AgentMPPlannerConfig(planner_config=_new_ompl_cfg)

        # Share PRM* roadmap — first call loads the file; subsequent calls
        # (every episode reset) inject the cached object at zero I/O cost.
        if not load_and_share_roadmap(self.sim, self.scenario.name):
            self.sim.logger.warning(
                f"No PRM* roadmap for '{self.scenario.name}' — build one first."
            )

        self._build_free_positions()

        obs  = self._get_obs()
        info = {}
        return obs, info

    # ------------------------------------------------------------------
    def step(self, action):
        # agents_list must be fixed before any sim calls so start positions are captured.
        agents_list = list(self.sim.agents.values())
        agent_starts = [(float(a.container.x), float(a.container.y)) for a in agents_list]

        predicted_positions = self._assign_subgoals(action) if self.n_subgoals > 0 else []

        # Cache task refs before the loop — SubgoalManager._complete_task() clears
        # agent.assigned_task mid-step, which would cause us to miss completion events.
        task_conts = [agent.assigned_task for agent in agents_list]

        self.sim.start_mp()
        self.sim.start_exe()

        individual_times = [None] * self.n_agents  # step at which each agent reached its goal
        terminated = False

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

        total_ompl_wall_time = sum(a.sgm._total_ompl_wall_time for a in agents_list)
        n_failed_plans = sum(a.sgm._failed_plans for a in agents_list)

        reward = self._compute_reward(
            terminated, makespan, individual_times, predicted_positions,
            agent_starts=agent_starts,
            task_goals=task_conts,
            diversity_sigma=self.diversity_sigma,
            diversity_bonus=self.diversity_bonus,
            skip_penalty=self.skip_penalty,
            failed_plan_penalty=self.failed_plan_penalty,
            n_failed_plans=n_failed_plans,
        )

        _y_wall = float(self.scenario.gap_geometry['y_wall'])
        info = {
            'terminated':          terminated,
            'makespan':            makespan,
            'n_failed':            sum(agent.sgm._failed_plans      for agent in self.sim.agents.values()),
            'n_skipped_subgoals':  sum(agent.sgm._skipped_subgoals  for agent in self.sim.agents.values()),
            'n_crossed':           sum(
                1 for agent in self.sim.agents.values()
                if agent.assigned_task is None or agent.container.y <= _y_wall
            ),
            'n_reached_subgoals':  sum(
                max(0, agent.sgm._subgoal_idx - agent.sgm._skipped_subgoals)
                for agent in self.sim.agents.values()
            ),
            'plan_wall_time':      total_ompl_wall_time,
        }

        return obs, reward, terminated, truncated, info
            
    # ------------------------------------------------------------------
    def _build_free_positions(self):
        """Delegate to the shared build_free_positions() — single source of truth."""
        self._free_positions = build_free_positions(
            self.sim, self.scenario.gap_geometry, self.grid_stride,
            subgoal_limits=self.scenario.subgoal_limits,
        )
        self.action_space = spaces.MultiDiscrete(
            np.array([[len(self._free_positions), len(self.wait_times)]] * (self.n_agents * self.n_subgoals)).flatten()
            if self.n_subgoals > 0 else np.array([1])
        )

    # ------------------------------------------------------------------
    def _compute_gap_vectors(self, agent_x: float, agent_y: float) -> np.ndarray:
        """(Δx, Δy) from agent to each gap center, flattened. Shape: (n_gaps*2,)."""
        gap_geometry = self.scenario.gap_geometry
        y_wall = float(gap_geometry['y_wall'])
        result = []
        for g in gap_geometry['gaps']:
            result.append(float(g['x_center']) - agent_x)
            result.append(y_wall - agent_y)
        return np.array(result, dtype=np.float32)

    # ------------------------------------------------------------------
    def _assign_subgoals(self, action: np.ndarray) -> list[tuple[float, float]]:
        """Decode (pos_idx, wait) per agent×subgoal, inject subgoals, return positions.

        Discrete: wait slot is an integer bin index into self.wait_times.
        Continuous: wait slot is a float in seconds directly (output of Normal head).
        """
        decoded = action.reshape(self.n_agents, self.n_subgoals, 2)
        positions = []
        for agent, agent_sgs in zip(self.sim.agents.values(), decoded):
            subgoal_coords, wait_ticks = [], []
            for a_pos, a_wait in agent_sgs:
                sx, sy = self._free_positions[int(a_pos)]
                subgoal_coords.append(np.array([float(sx), float(sy), 0.0]))
                if self.wait_mode == 'continuous':
                    wait_ticks.append(int(float(a_wait) / self.sim.Ts))
                else:
                    wait_ticks.append(int(self.wait_times[int(a_wait)] / self.sim.Ts))
                positions.append((float(sx), float(sy)))
            agent.sgm.set_subgoals(subgoal_coords, wait_ticks=wait_ticks)
        return positions

    # ------------------------------------------------------------------
    def _get_obs(self) -> dict:
        return build_subgoal_obs(self.sim, self.scenario.gap_geometry)

    # ------------------------------------------------------------------
    @staticmethod
    def _agent_to_xy(cont: FRODOAgentContainer) -> np.ndarray:
        return np.array([cont.x, cont.y, cont.psi], dtype=np.float32)

    @staticmethod
    def _goal_to_xy(cont) -> np.ndarray:
        return np.array([cont.x, cont.y], dtype=np.float32)


    # ------------------------------------------------------------------
    def _compute_reward(
        self,
        terminated: bool,
        makespan: int,
        individual_times: list[int | None],
        predicted_positions: list[tuple[float, float]],
        agent_starts: list[tuple[float, float]] | None = None,
        task_goals: list | None = None,
        alpha: float = 0.3,
        beta: float = 1.0,
        crossing_bonus: float = 1.5,
        # subgoal_bonus set to 0: rewarding any reached subgoal regardless of position
        # created a perverse incentive — policy converged to easy-to-reach top-corner
        # positions far from the gap to cheaply earn the bonus.
        subgoal_bonus: float = 0.0,
        # skip_penalty: penalises subgoals the planner could not reach (planning failure).
        # Applied uniformly in BOTH terminated and truncated branches — skipping is
        # bad regardless of episode outcome. The bypass exploit (predict gap-edge
        # subgoal → skip → OMPL direct route → task done) must be closed in the
        # terminated branch where the 30-point bonus otherwise dwarfs the penalty.
        # Energy_penalty alone does not stop this (gap-edge positions are collinear
        # with start→goal and thus incur near-zero extra path length).
        skip_penalty: float = 4.0,
        failed_plan_penalty: float = 0.0,
        n_failed_plans: int = 0,
        diversity_bonus: float = 1.5,
        diversity_sigma: float = 0.35,
        energy_weight: float = 2.0,
    ) -> float:
        """Compute reward signal.

        Terminated: fast completion dominates.  makespan_frac is replaced by
        effective_makespan_frac which folds in OMPL wall time (decentralised
        factor 2/N) so that replanning is penalised even though sim steps
        don't advance during blocking OMPL solves.

        Truncated: gap-aware distance fallback with energy penalty replacing
        the former progress term.

        Parameters
        ----------
        alpha:           weight of individual times relative to makespan (terminated)
        beta:            scale of distance penalty (truncated)
        crossing_bonus:  per-agent reward for crossing the dividing wall (truncated)
        subgoal_bonus:   per-agent reward for reaching the predicted subgoal (truncated)
        skip_penalty:    per-agent penalty for each skipped (unreachable) subgoal (both branches)
        diversity_bonus: scale of pairwise Gaussian repulsion between predicted subgoals
        diversity_sigma: bandwidth of the Gaussian kernel in metres
        energy_weight:   scale of the extra-path-length penalty (truncated)
        """
        # Count skips before branching — needed in both terminated and truncated.
        n_skipped_subgoals = sum(a.sgm._skipped_subgoals for a in self.sim.agents.values())

        # All tasks completed ---------------------------------------------------
        if terminated:
            # Normalise to [0, 1] relative to max_steps so the termination bonus
            # always dominates truncated reward (max truncated ≈ crossing_bonus × N ≈ 7.5;
            # min terminated ≈ 30 - 10 - 3 = 17 >> 7.5).
            # Wall-clock OMPL time is intentionally excluded: it is CPU/scheduler-dependent
            # and therefore noisy. Failed plans are penalised directly via failed_plan_penalty.
            makespan_frac = min(1.0, makespan / self.max_steps)
            mean_indiv_frac = float(np.mean([t / self.max_steps for t in individual_times]))
            return (30.0
                    - 10.0 * makespan_frac
                    - alpha * 10.0 * mean_indiv_frac
                    - skip_penalty * n_skipped_subgoals
                    - failed_plan_penalty * n_failed_plans)

        # Truncated: gap-aware distance + crossing/subgoal/diversity bonuses ---
        gap_geometry = self.scenario.gap_geometry
        y_wall       = float(gap_geometry['y_wall'])
        gaps         = gap_geometry['gaps']

        n_crossed          = 0
        n_reached_subgoals = 0
        total_dist         = 0.0
        crossed_xs         = []
        for agent in self.sim.agents.values():
            n_reached_subgoals += max(0, agent.sgm._subgoal_idx - agent.sgm._skipped_subgoals)
            ax, ay = agent.container.x, agent.container.y

            if agent.assigned_task is None:
                # Task completed — agent crossed the wall (by moving through the passage)
                n_crossed += 1
                crossed_xs.append(ax)
                continue

            tx, ty = agent.assigned_task.x, agent.assigned_task.y
            dist   = float(np.hypot(ax - tx, ay - ty))
            if ay > y_wall and gaps:
                # Still above wall: add horizontal misalignment from nearest gap
                dist += min(abs(ax - g['x_center']) for g in gaps)
            elif ay <= y_wall:
                n_crossed += 1
                crossed_xs.append(ax)
            total_dist += dist

        # Gaussian pairwise repulsion: penalise pairs of predicted subgoals that are close
        repulsion = sum(
            float(np.exp(-np.hypot(predicted_positions[i][0] - predicted_positions[j][0],
                                   predicted_positions[i][1] - predicted_positions[j][1]) ** 2
                         / (2 * diversity_sigma ** 2)))
            for i in range(len(predicted_positions))
            for j in range(i + 1, len(predicted_positions))
        )

        # Energy penalty: extra path length introduced by the subgoal detour.
        # extra_i = d(start→sg) + d(sg→goal) − d(start→goal) ≥ 0 by triangle inequality.
        # Identity subgoal (sg = start, wait=0) costs exactly 0 — a valid no-op for the
        # first-through-gap agent.  Orthogonal subgoals incur large penalties.
        # Normalised by N × arena_diag so the scale matches other truncated terms.
        energy_penalty = 0.0
        if (agent_starts is not None and task_goals is not None
                and self.n_subgoals > 0 and predicted_positions):
            lim = self.scenario.limits
            arena_diag = float(np.hypot(lim[0][1] - lim[0][0], lim[1][1] - lim[1][0]))
            raw_extra = 0.0
            for i, (sx_start, sy_start) in enumerate(agent_starts):
                tc = task_goals[i] if i < len(task_goals) else None
                if tc is None:
                    continue
                sg_idx = i * self.n_subgoals
                if sg_idx >= len(predicted_positions):
                    continue
                sx_sg, sy_sg = predicted_positions[sg_idx]
                d_start_sg   = float(np.hypot(sx_start - sx_sg,  sy_start - sy_sg))
                d_sg_goal    = float(np.hypot(sx_sg    - tc.x,   sy_sg    - tc.y))
                d_start_goal = float(np.hypot(sx_start - tc.x,   sy_start - tc.y))
                raw_extra += d_start_sg + d_sg_goal - d_start_goal
            energy_penalty = energy_weight * raw_extra / (self.n_agents * arena_diag)

        return (
            - beta           * total_dist
            + crossing_bonus * n_crossed
            + subgoal_bonus  * n_reached_subgoals
            - skip_penalty          * n_skipped_subgoals
            - failed_plan_penalty   * n_failed_plans
            - energy_penalty
            - diversity_bonus * repulsion
        )

    def render(self):
        ...

    def close(self):
        ...