from typing import List

from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS

from master_thesis.general.general_agents import FRODOGeneralAgent, FRODO_Agent_Config
from master_thesis.general.general_simulation import FrodoGeneralEnvironment
from master_thesis.motion_planning.mp_agent import MPAgentModule
from master_thesis.task_assignment.ta_agent import TAAgentModule
from master_thesis.containers.ta_container import AgentTAContainer, AgentTAConfig, AgentTAState


class FRODOUniversalAgent(FRODOGeneralAgent):
    mpi: MPAgentModule
    asi: TAAgentModule
    exi: ...

    def __init__(self, env_config, agent_id: str, Ts=0.1, start_config=(0.0,0.0,0.0), color: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> None:
        super().__init__(agent_id=agent_id, Ts=Ts, start_config=start_config, color=color)

        # Create task assignment container with default config and state
        ta_config = AgentTAConfig()
        ta_state = AgentTAState()
        ta_container = AgentTAContainer(config=ta_config, state=ta_state)

        # MPAgent module
        self.mpi = MPAgentModule(
            agent_config=self.container, 
            env_container=env_config, 
            runner=self.runner, 
            logger=self.logger)

        # Assignment Agent module
        self.asi = TAAgentModule(
            agent_id=agent_id,
            agent_container=self.container,
            ta_container=ta_container,
            logger=self.logger,
        )

        self.exi = ... # TODO

    def setup_scheduling(self):
        """Override to add task assignment and motion planning actions"""
        super().setup_scheduling()

        # Attach task assignment to PREDICTION phase (priority 21 - runs before dynamics)
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.LOGIC].addAction(self._action_task_assignment)

        # Attach motion planning to PREDICTION phase (runs after task assignment in same phase)
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.LOGIC].addAction(self._action_motion_planning)

    def _action_task_assignment(self):
        ...

    def _action_motion_planning(self):
        ...

# def main():
#     ...

# if __name__ == "__main__":
#     main()

