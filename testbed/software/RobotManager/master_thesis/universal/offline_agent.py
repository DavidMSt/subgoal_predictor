"""FRODOOfflineAgent — OMPL trajectory planner + trajectory playback pipeline."""

from master_thesis.universal.universal_agent import FRODOUniversalAgent
from master_thesis.modules.motion_planning.path_planner_base import PathPlannerBase
from master_thesis.modules.execution.motion_executor_base import MotionExecutorBase


class FRODOOfflineAgent(FRODOUniversalAgent):
    """
    Agent that plans globally with OMPL and plays back the resulting
    trajectory.  This is the classic OFFLINE pipeline.

    Usage::

        sim.new_agent('a1', agent_class=FRODOOfflineAgent)
        # or simply (it's the default):
        sim.new_agent('a1')
    """

    def _build_pipeline(self) -> tuple[PathPlannerBase, MotionExecutorBase]:
        from master_thesis.modules.motion_planning.ompl_trajectory_planner import OMPLTrajectoryPlanner
        from master_thesis.modules.execution.trajectory_executor import TrajectoryExecutor

        planner = OMPLTrajectoryPlanner(
            agent_cont=self.container,
            lwr_cont=None,
            logger=self.logger,
        )
        executor = TrajectoryExecutor(
            agent_cont=self.container,
            logger=self.logger,
        )
        return planner, executor
