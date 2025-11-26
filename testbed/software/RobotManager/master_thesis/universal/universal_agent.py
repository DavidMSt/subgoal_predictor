from typing import List
from master_thesis.general.general_agents import FRODOGeneralAgent, FRODO_Agent_Config
from master_thesis.general.general_simulation import FrodoGeneralEnvironment
from master_thesis.motion_planning.mp_agent import MPAgentModule
from master_thesis.task_assignment.task_agent import AssignmentAgentModule


class FRODOUniversalAgent(FRODOGeneralAgent):
    mpi: MPAgentModule
    asi: AssignmentAgentModule
    exi: ...

    def __init__(self, env_config, agent_id: str, Ts=None, agent_config: FRODO_Agent_Config | None = None, start_config=(0.0,0.0,0.0), *args, **kwargs) -> None:
        super().__init__(agent_id = agent_id, Ts = Ts, agent_config = agent_config, start_config =  start_config)
        
        assert isinstance(agent_config, FRODO_Agent_Config) # if not provided as argument, will be created by class constructor with default values
        
        self.mpi = MPAgentModule(agent_config= agent_config, env_config= env_config, runner=self.runner, logger = self.logger)
        self.asi = AssignmentAgentModule(agent_id=agent_id, logger=self.logger)
        self.exi = ... # TODO


# def main():
#     ...

# if __name__ == "__main__":
#     main()

