from typing import List
from master_thesis.general.general_agents import FRODOGeneralAgent, FRODO_Agent_Config
from master_thesis.general.general_simulation import FrodoGeneralEnvironment
from master_thesis.motion_planning.mp_agent import MPAgentModule
from master_thesis.task_assignment.task_agent import AssignmentAgentModule


class FRODOUniversalAgent(FRODOGeneralAgent):
    mpi: MPAgentModule
    asi: AssignmentAgentModule
    exi: ...

    def __init__(self, env_config, agent_id: str, Ts=None, start_config=(0.0,0.0,0.0), color=None, *args, **kwargs) -> None:
        super().__init__(agent_id=agent_id, Ts=Ts, start_config=start_config, color=color)
        
        # MPAgent module
        self.mpi = MPAgentModule(agent_config=self.container, env_container=env_config, runner=self.runner, logger=self.logger)
        self.asi = AssignmentAgentModule(agent_id=agent_id, logger=self.logger, get_state_fun=self._get_state)
        self.exi = ... # TODO


# def main():
#     ...

# if __name__ == "__main__":
#     main()

