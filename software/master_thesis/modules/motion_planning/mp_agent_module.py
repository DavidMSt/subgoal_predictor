# 3rd party
import numpy as np
from typing import Type

# bilbolab
from core.utils.logging_utils import Logger

# master thesis
from master_thesis.modules.motion_planning.helper.ompl_planner import OMPLPlannerFRODOKino, OMPLPlannerFRODOBase

from master_thesis.containers.general_containers.frodo_agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.local_world_container import LocalWorldContainer
from master_thesis.containers.module_containers.mp_containers.mp_phase_container import MPPhaseContainer, MPPhaseConfig
from master_thesis.containers.module_containers.mp_containers.mp_planner_container import AgentMPPlannerConfig, AgentMPPlannerContainer
from master_thesis.containers.general_containers.task_container import TaskContainer
from master_thesis.containers.base_container import BaseContainer

# TODO: Apply offset bidirectional from ompl to simulation and from simulation back (initialization of start config)

class MPAgentModule():
    lwr_cont: LocalWorldContainer | None
    agent_cont: FRODOAgentContainer

    def __init__(self,agent_cont: FRODOAgentContainer, lwr_cont: LocalWorldContainer | None, logger: Logger, mp_type: Type[OMPLPlannerFRODOBase] = OMPLPlannerFRODOKino) -> None:
        self.agent_cont = agent_cont
        self.lwr_cont = lwr_cont
        self.logger = logger
        self.mp_type = mp_type
        self.motion_planner = None
        self.planner_cont = self.setup_mp_container()

    def plan_motion(self, phase_key: str, goal_task: TaskContainer| None, start_task: TaskContainer | None = None):
        def extract_config_from_cont(container: BaseContainer):
            state = [container.x, container.y, container.psi]
            return state

        if self.motion_planner is None:
            self.motion_planner = self.setup_motion_planner()
        
        # if no start specified use the current agent config
        if start_task == None:
            # use current agent state as start config
            agent_state = extract_config_from_cont(self.agent_cont)
            start_config = np.array(agent_state)

        # if start specified, e.g. to predict path between two tasks
        else: 
            task_state = extract_config_from_cont(start_task)
            start_config = np.array(task_state)

        assert isinstance(goal_task, TaskContainer)
        goal_config = np.array(extract_config_from_cont(goal_task))
        
        # update the mp container
        self.planner_cont.start = start_config
        self.planner_cont.goal = goal_config

        solved, path_length = self.motion_planner.solve_problem()

        if solved:
            solution_cont = self.motion_planner._create_solution_cont()
            
            self.planner_cont.phases[phase_key] = solution_cont

            self.logger.info(
                f"Found solution with {len(solution_cont.states)} states, "
                f"total length {path_length}, end config: {solution_cont.states[-1]}"
            )
        else:
            self.logger.warning(f"No solution found! timeout reached")

    def setup_mp_container(self):
        config = AgentMPPlannerConfig() # TODO: Offer choice to make more adjustments when calling the function
        mp_container = AgentMPPlannerContainer(config = config, logger=self.logger)
        return mp_container

    def setup_motion_planner(self):
        # TODO: initialize the planner once, but still be able to dynamically handle obstacles in the environment to enable obstacle creation after agent creation
        motion_planner = self.mp_type(mp_container=self.planner_cont, agent_container=self.agent_cont, lwr_container=self.lwr_cont)
        return motion_planner

if __name__ == "__main__":

    from robots.frodo.simulation.frodo import FRODO_State
    from master_thesis.containers.general_containers.task_container import Task_Config
    from master_thesis.containers.general_containers.obstacle_container import Obstacle_Config, ObstacleContainer
    from master_thesis.containers.general_containers.local_world_container import LocalWorldContainer, LocalWorldConfig, LocalWorldState

    agent_cont = FRODOAgentContainer(agent_id='mpm_mock_frodo', state=FRODO_State(0.0, 0.0, 0.0, 0.0, 0.0))
    task_cont =TaskContainer(object_id = 'mpm_mock_task', config= Task_Config(5.0, 0.0, 0.0))
    obstacle_cont = ObstacleContainer(object_id = 'mpm_mock_obstacle', config = Obstacle_Config(x = 2.0, length= 1.0, width = 1.0, height = 1.0))

    lwr_cont = LocalWorldContainer(
        config=LocalWorldConfig(limits=((-5.0, 5.0), (-5.0, 5.0))),
        state= LocalWorldState(neighbors= {}, obstacles={obstacle_cont.object_id, obstacle_cont}, tasks= {task_cont.object_id, task_cont})
        )

    mpm = MPAgentModule(agent_cont=agent_cont, task_cont = task_cont)