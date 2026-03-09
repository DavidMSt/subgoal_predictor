# 3rd party
import numpy as np

# bilbolab
from core.utils.logging_utils import Logger

# master thesis
from master_thesis.modules.motion_planning.mp_functions.ompl_planner import OMPLSmoothPathPlanner
from master_thesis.modules.motion_planning.ompl_trajectory_planner import _obs_to_dicts, _traj_dict_to_container

from master_thesis.containers.general_containers.frodo_agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.local_world_container import LocalWorldContainer
from master_thesis.containers.module_containers.mp_containers.mp_planner_container import AgentMPPlannerConfig, AgentMPPlannerContainer
from master_thesis.containers.general_containers.task_container import TaskContainer


class MPAgentModule():
    lwr_cont: LocalWorldContainer | None
    agent_cont: FRODOAgentContainer

    def __init__(self, agent_cont: FRODOAgentContainer, lwr_cont: LocalWorldContainer | None, logger: Logger) -> None:
        self.agent_cont = agent_cont
        self.lwr_cont = lwr_cont
        self.logger = logger
        self.motion_planner: OMPLSmoothPathPlanner | None = None
        self.planner_cont = self.setup_mp_container()

    def plan_motion(self, phase_key: str, goal_task: TaskContainer | None, start_task: TaskContainer | None = None):
        if self.motion_planner is None:
            self.motion_planner = self.setup_motion_planner()

        if start_task is None:
            start_config = np.array([self.agent_cont.x, self.agent_cont.y, self.agent_cont.psi])
        else:
            start_config = np.array([start_task.x, start_task.y, start_task.psi])

        assert isinstance(goal_task, TaskContainer)
        goal_config = np.array([goal_task.x, goal_task.y, goal_task.psi])

        obs_dicts = _obs_to_dicts(self.lwr_cont)
        self.motion_planner._collision_checker.refresh_env_manager(obstacles=obs_dicts)

        solved, path_length = self.motion_planner.solve(start_config, goal_config)

        if solved:
            solution_cont = _traj_dict_to_container(self.motion_planner.get_solution())
            self.planner_cont.phases[phase_key] = solution_cont
            self.logger.info(
                f"Found solution with {len(solution_cont.states)} states, "
                f"total length {path_length}, end config: {solution_cont.states[-1]}"
            )
        else:
            self.logger.warning("No solution found! timeout reached")

    def setup_mp_container(self):
        config = AgentMPPlannerConfig()
        return AgentMPPlannerContainer(config=config, logger=self.logger)

    def setup_motion_planner(self) -> OMPLSmoothPathPlanner:
        return OMPLSmoothPathPlanner(
            limits=self.lwr_cont.config.limits,
            obstacles=_obs_to_dicts(self.lwr_cont),
            agent_dims=(self.agent_cont.length, self.agent_cont.width, self.agent_cont.height),
            config=self.planner_cont.config.planner_config,
        )
