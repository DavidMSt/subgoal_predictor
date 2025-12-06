from typing import List

from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS

from master_thesis.general.general_agents import FRODOGeneralAgent, FRODO_Agent_Config
from master_thesis.motion_planning.mp_agent import MPAgentModule
from master_thesis.task_assignment.ta_agent import TAAgentModule

from master_thesis.containers.environment_containers import EnvironmentContainer
from master_thesis.containers.ta_container import AgentTAContainer, AgentTAConfig, AgentTAState
from master_thesis.containers.mp_container import AgentMPContainer
from master_thesis.containers.exe_container import ExecutionContainer


class FRODOUniversalAgent(FRODOGeneralAgent):
    mpi: MPAgentModule
    tai: TAAgentModule
    exe: ...

    def __init__(self, env_container, agent_id: str, Ts=0.1, start_config=(0.0,0.0,0.0), color: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> None:
        super().__init__(agent_id=agent_id, Ts=Ts, start_config=start_config, color=color)

        # ------------------------------------------------------------------
        # MODULE RELATED CONTAINERS
        # ------------------------------------------------------------------

        # Create task assignment container with default config and state
        ta_container = AgentTAContainer()
        mp_container = AgentMPContainer()
        exe_container = ExecutionContainer()
     
        # ------------------------------------------------------------------
        # MODULES
        # ------------------------------------------------------------------

        # MPAgent module
        self.mpi = MPAgentModule(
            agent_config=self.container, 
            env_container=env_container, 
            runner=self.runner, 
            logger=self.logger)

        # TAAgent module
        self.tai = TAAgentModule(
            agent_id=agent_id,
            agent_container=self.container,
            ta_container=ta_container,
            logger=self.logger,
        )

        self.exe = ... # TODO

    def setup_scheduling(self):
        """Override to add task assignment and motion planning actions"""
        super().setup_scheduling()

        # Attach task assignment action
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.LOGIC].addAction(self._action_task_assignment)

        # Attach motion planning action
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.LOGIC].addAction(self._action_motion_planning)

    def _action_task_assignment(self):
        if self.tai.ta_container.state.mode != "decentral":
            return  # Centralized mode - skip TA
        if self.tai.ta_container.state.assigned_task is not None:
            return  # Already have task
        if not self.tai.assignment_pending:
            return  # No assignment requested
        # ... do assignment

    def _action_motion_planning(self):
        if self.tai.ta_container.state.assigned_task is None:
            return  # No task to plan for
        if self.runner.active != "idle":
            return  # Already executing
        # ... do planning



def main():
    import time
    from master_thesis.general.general_simulation import FRODO_general_Simulation
    from master_thesis.general.general_tasks import GeneralTask

    # Initialize Sim
    sim = FRODO_general_Simulation()
    sim.init()

    # Initialize Agent
    agent = FRODOUniversalAgent(agent_id = 'frodo01', env_container=sim.environment.environment_container ,start_config= (0.0,0.0,0.0))
    sim.add_agent(agent)

    # Initialize Task
    task = GeneralTask(id='mock_task', x = 2, y = 2, psi = 0)

    # publish task manually to the agents ta module
    agent.tai.add_tasks(tuple([task]))

    sim.start()

    

    while True:
        time.sleep(10)
if __name__ == "__main__":
    main()

