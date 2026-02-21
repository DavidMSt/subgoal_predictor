"""FRODOReactiveAgent — Direct Goal + MPPI reactive pipeline."""

from master_thesis.universal.universal_agent import FRODOUniversalAgent
from master_thesis.modules.motion_planning.path_planner_base import PathPlannerBase
from master_thesis.modules.execution.motion_executor_base import MotionExecutorBase


class FRODOReactiveAgent(FRODOUniversalAgent):
    """
    Agent that navigates reactively: the task goal is passed straight
    through as a subgoal and an MPPI controller drives toward it.

    Usage::

        sim.new_agent('a1', agent_class=FRODOReactiveAgent)
        # or with custom MPPI params:
        sim.new_agent('a1', agent_class=FRODOReactiveAgent, mppi_horizon=50)
    """

    def __init__(self, env_container, agent_id, Ts=0.1, start_config=(0.0, 0.0, 0.0),
                 color=(1.0, 1.0, 1.0), log_level='INFO',
                 mppi_horizon: int = 30,
                 mppi_n_samples: int = 100,
                 replan_interval: int = 1):
        # Store before super().__init__ which calls _build_pipeline()
        self._mppi_horizon = mppi_horizon
        self._mppi_n_samples = mppi_n_samples
        self._replan_interval = replan_interval
        super().__init__(env_container, agent_id, Ts, start_config, color, log_level)

    def _build_pipeline(self) -> tuple[PathPlannerBase, MotionExecutorBase]:
        from master_thesis.modules.motion_planning.direct_goal_planner import DirectGoalPlanner
        from master_thesis.modules.execution.reactive_executor import ReactiveExecutor
        from master_thesis.modules.local_control.mppi_controller import MPPIConfig, MPPIController

        planner = DirectGoalPlanner(
            agent_cont=self.container,
            lwr_cont=None,
            logger=self.logger,
        )

        mppi_config = MPPIConfig(
            dt=self.container.Ts,
            horizon=self._mppi_horizon,
            n_samples=self._mppi_n_samples,
        )
        executor = ReactiveExecutor(
            agent_cont=self.container,
            controller=MPPIController(mppi_config),
            lwr_cont=None,
            logger=self.logger,
            replan_interval=self._replan_interval,
        )
        return planner, executor
