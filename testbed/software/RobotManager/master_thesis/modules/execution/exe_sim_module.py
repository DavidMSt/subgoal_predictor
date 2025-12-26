# bilbolab
from core.utils.logging_utils import Logger

# master thesis
from master_thesis.containers.module_containers.exe_containers.exe_container import AgentExeContainer

class ExeSimulationModule():
    agent_exe_conts : dict[str, AgentExeContainer]
    logger: Logger

    def __init__(self,
                 agent_exe_conts : dict[str, AgentExeContainer], 
                 logger: Logger) -> None: #TODO: should not receive agents here directly? 
        self.agent_exe_conts = agent_exe_conts
        self.logger = logger

    def start_execution(self, phase_name = 'example_mp_phase'):
        agent_exe_conts = self.agent_exe_conts
        if not agent_exe_conts:
            self.logger.error('MP Module coudld not find MP agent containers')
        for name, exe_cont in agent_exe_conts.items():
            exe_cont.start_execution = True
