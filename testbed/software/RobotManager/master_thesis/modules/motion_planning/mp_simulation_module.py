# bilbolab
from core.utils.logging_utils import Logger

# master thesis
from master_thesis.modules.motion_planning.mp_agent_module import MPAgentModule
from master_thesis.containers.module_containers.mp_containers.mp_planner_container import AgentMPPlannerContainer
from master_thesis.general.general_agent import FRODOGeneralAgent
from master_thesis.containers.general_containers.task_container import TaskContainer

class MPSimulationModule():
    agent_mp_conts : dict[str, AgentMPPlannerContainer]
    logger: Logger

    def __init__(self,
                 agent_mp_conts : dict[str, AgentMPPlannerContainer], 
                 logger: Logger) -> None: #TODO: should not receive agents here directly? 
        self.agent_mp_conts = agent_mp_conts
        self.logger = logger

    def start_motion_planning(self, phase_name = 'example_mp_phase'):
        agent_mp_conts = self.agent_mp_conts
        if not agent_mp_conts:
            self.logger.error('MP Module coudld not find MP agent containers')
        for _, mp_cont in agent_mp_conts.items():
            mp_cont.start_planning = phase_name