"""PathPlannerBase that predicts subgoals from a trained RL policy (SB3)."""

from __future__ import annotations

import numpy as np
from core.utils.logging_utils import Logger

from master_thesis.modules.motion_planning.path_planner_base import PathPlannerBase, PlanResult
from master_thesis.containers.general_containers.frodo_agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.local_world_container import LocalWorldContainer
from master_thesis.containers.general_containers.task_container import TaskContainer


class RLSubgoalPredictor(PathPlannerBase):
    """
    Loads a trained SB3 model and uses it to predict subgoals.

    Observation construction mirrors SubgoalRLEnv._get_obs() so that
    the model receives the same feature vector it was trained on.
    """

    _AGENT_DIM = 5
    _GOAL_DIM = 3
    _NEIGHBOR_DIM = 5
    _OBSTACLE_DIM = 3

    def __init__(
        self,
        agent_cont: FRODOAgentContainer,
        lwr_cont: LocalWorldContainer | None,
        logger: Logger,
        model_path: str | None = None,
        replan_interval: int = 50,
        subgoal_range: float = 3.0,
        max_neighbors: int = 4,
        max_obstacles: int = 4,
    ):
        super().__init__(agent_cont, lwr_cont, logger)
        self.model_path = model_path
        self.replan_interval = replan_interval
        self.subgoal_range = subgoal_range
        self.max_neighbors = max_neighbors
        self.max_obstacles = max_obstacles

        self._model = None
        self._tick_counter = 0

        if model_path is not None:
            self._load_model(model_path)

    # ── PathPlannerBase interface ───────────────────────────────────

    def plan(self, goal_task: TaskContainer, phase_key: str = 'default',
             explicit_start=None, use_roadmap: bool = True) -> PlanResult:
        goal = np.array([goal_task.x, goal_task.y, goal_task.psi])
        obs = self._build_obs(goal)

        if self._model is None:
            self.logger.warning("RLSubgoalPredictor: no model loaded, falling back to direct goal")
            return PlanResult(success=True, subgoal=goal, requires_reactive=True)

        action, _ = self._model.predict(obs, deterministic=True)
        subgoal = self._action_to_subgoal(action)
        self._tick_counter = 0

        self.logger.debug(f"RLSubgoalPredictor: subgoal = {subgoal}")
        return PlanResult(success=True, subgoal=subgoal, requires_reactive=True)

    def needs_replan(self) -> bool:
        self._tick_counter += 1
        return self._tick_counter >= self.replan_interval

    # ── Observation (mirrors SubgoalRLEnv._get_obs) ─────────────────

    def _build_obs(self, goal: np.ndarray) -> np.ndarray:
        ac = self.agent_cont
        parts: list[np.ndarray] = []

        # Own agent
        parts.append(np.array([ac.x, ac.y, ac.psi, ac.state.v, ac.state.psi_dot], dtype=np.float32))

        # Goal
        parts.append(goal.astype(np.float32))

        # Neighbors (padded)
        neighbor_obs = np.zeros(self.max_neighbors * self._NEIGHBOR_DIM, dtype=np.float32)
        if self.lwr_cont is not None and hasattr(self.lwr_cont, 'neighbors'):
            for i, (_, nc) in enumerate(sorted(self.lwr_cont.neighbors.items())):
                if i >= self.max_neighbors:
                    break
                off = i * self._NEIGHBOR_DIM
                neighbor_obs[off: off + 5] = [nc.state.x, nc.state.y, nc.state.psi,
                                               nc.state.v, nc.state.psi_dot]
        parts.append(neighbor_obs)

        # Obstacles (padded)
        obstacle_obs = np.zeros(self.max_obstacles * self._OBSTACLE_DIM, dtype=np.float32)
        if self.lwr_cont is not None and hasattr(self.lwr_cont, 'obstacles') and self.lwr_cont.obstacles:
            for i, (_, oc) in enumerate(sorted(self.lwr_cont.obstacles.items())):
                if i >= self.max_obstacles:
                    break
                off = i * self._OBSTACLE_DIM
                obstacle_obs[off: off + 3] = [oc.x, oc.y, getattr(oc, 'radius', 0.3)]
        parts.append(obstacle_obs)

        return np.concatenate(parts)

    # ── Helpers ─────────────────────────────────────────────────────

    def _action_to_subgoal(self, action: np.ndarray) -> np.ndarray:
        ac = self.agent_cont
        dx = float(action[0]) * self.subgoal_range
        dy = float(action[1]) * self.subgoal_range
        return np.array([ac.x + dx, ac.y + dy, 0.0])

    def _load_model(self, path: str):
        try:
            from stable_baselines3 import PPO
            self._model = PPO.load(path)
            self.logger.info(f"RLSubgoalPredictor: loaded model from {path}")
        except Exception as e:
            self.logger.warning(f"RLSubgoalPredictor: failed to load model from {path}: {e}")
            self._model = None

    def load_model(self, path: str):
        """Public API to (re-)load a model checkpoint."""
        self.model_path = path
        self._load_model(path)
