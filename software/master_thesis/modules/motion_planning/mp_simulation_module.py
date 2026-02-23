# bilbolab
from core.utils.logging_utils import Logger

# master thesis
from master_thesis.containers.module_containers.mp_containers.mp_planner_container import AgentMPPlannerContainer

class MPSimulationModule():
    agent_mp_conts : dict[str, AgentMPPlannerContainer]
    logger: Logger

    def __init__(self,
                 agent_mp_conts : dict[str, AgentMPPlannerContainer], 
                 logger: Logger) -> None:
        self.agent_mp_conts = agent_mp_conts
        self.logger = logger

    def start_motion_planning(self, phase_name = 'example_mp_phase'):
        agent_mp_conts = self.agent_mp_conts

        for _, mp_cont in agent_mp_conts.items():
            mp_cont.start_planning = phase_name