"""FRODORLAgent — RL Subgoal Predictor + OMPL offline pipeline (matches training)."""

from master_thesis.universal.universal_agent import FRODOUniversalAgent
from master_thesis.modules.motion_planning.path_planner_base import PathPlannerBase
from master_thesis.modules.execution.motion_executor_base import MotionExecutorBase


class FRODORLAgent(FRODOUniversalAgent):
    """
    Agent that uses a trained RL policy to predict intermediate subgoals
    and OMPL+Bézier to execute each segment — identical to the training pipeline.

    Usage::

        sim.new_agent('a1', agent_class=FRODORLAgent,
                      rl_model_path='checkpoints/subgoal_policy.pt')
    """

    def __init__(self, env_container, agent_id, Ts=0.1, start_config=(0.0, 0.0, 0.0),
                 color=(1.0, 1.0, 1.0), log_level='INFO',
                 rl_model_path: str | None = None,
                 rl_replan_interval: int = 50):
        self._rl_model_path = rl_model_path
        self._rl_replan_interval = rl_replan_interval
        super().__init__(env_container, agent_id, Ts, start_config, color, log_level)

    def _build_pipeline(self) -> tuple[PathPlannerBase, MotionExecutorBase]:
        from master_thesis.modules.subgoal_predictor.rl_subgoal_predictor import RLSubgoalPredictor
        from master_thesis.modules.execution.trajectory_executor import TrajectoryExecutor

        planner = RLSubgoalPredictor(
            agent_cont=self.container,
            lwr_cont=None,
            logger=self.logger,
            model_path=self._rl_model_path,
            replan_interval=self._rl_replan_interval,
        )
        executor = TrajectoryExecutor(
            agent_cont=self.container,
            logger=self.logger,
        )
        return planner, executor
