# bilbolab
from core.utils.logging_utils import Logger

# master thesis
from master_thesis.motion_planning.mp_agent_module import MPAgentModule
from master_thesis.general.general_agents import FRODOGeneralAgent
from master_thesis.containers.general_containers.task_container import TaskContainer

class MPSimulationModule():
    agents: dict[str, FRODOGeneralAgent]
    logger: Logger

    def __init__(self, agents: dict[str, FRODOGeneralAgent], logger: Logger) -> None:
        self.agents = agents
        self.logger = logger

    def agent_motion_planning(self, agent: str | FRODOGeneralAgent, 
                              solution_phase_name: str, *, goal_task: TaskContainer, 
                              start_task: TaskContainer | None = None): # TODO: specify planner on this level already
        if isinstance(agent, str):
            agent = self.agents[agent]
        
        mpi = getattr(agent, 'mpi', None)
        if mpi is not None and isinstance(mpi, MPAgentModule):
            mpi.plan_motion(phase_key=solution_phase_name, start_task=start_task, goal_task=goal_task)
        else:
            if hasattr(agent, 'agent_id'):
                self.logger.error(f'Tried to plan motion for agent: {agent.agent_id}, no Motion planning interface present')
            else:
                self.logger.error(f'Tried to plan motion for agent, no Motion planning interface present')

    # def multiple_agents_motion_planning(self, goal_configs: list, start_configs: list |None = None):
    #     raise NotImplementedError
    #     agents = self.agents

    #     for agent in agents.values():
    #         if start_configs == None:
    #             start_config = agent.configuration
