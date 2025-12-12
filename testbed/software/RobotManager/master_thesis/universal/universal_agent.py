from typing import List

from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS

from master_thesis.general.general_agent import FRODOGeneralAgent, FRODO_Agent_Config
from master_thesis.motion_planning.mp_agent_module import MPAgentModule
from master_thesis.task_assignment.ta_agent_module import TAAgentModule
from master_thesis.execution.exe_agent_module import EXEAgentModule

from master_thesis.containers.general_containers.environment_container import EnvironmentContainer
from master_thesis.containers.module_containers.ta_containers.ta_container_agent import AgentTAContainer, AgentTAConfig, AgentTAState
from master_thesis.containers.module_containers.mp_container import AgentMPContainer
from master_thesis.containers.module_containers.exe_container import ExecutionContainer


class FRODOUniversalAgent(FRODOGeneralAgent):
    mpi: MPAgentModule
    tai: TAAgentModule
    exe: EXEAgentModule 

    def __init__(self, env_container, agent_id: str, Ts=0.1, start_config=(0.0,0.0,0.0), color: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> None:
        super().__init__(agent_id=agent_id, Ts=Ts, start_config=start_config, color=color)

        # ------------------------------------------------------------------
        # MODULE RELATED CONTAINERS
        # ------------------------------------------------------------------

        # Create task assignment container with default config and state
        ta_container = AgentTAContainer() # TODO: Only ta container needed here the other two could also be used in modules directly
        mp_container = AgentMPContainer()
        exe_container = ExecutionContainer()
     
        # ------------------------------------------------------------------
        # MODULES
        # ------------------------------------------------------------------

        # MPAgent module
        self.mpi = MPAgentModule(
            agent_cont=self.container, 
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

        self.exi = EXEAgentModule( # TODO: Implement this module
            logger = self.logger
        ) # TODO

    def setup_scheduling(self):
        """Override to add task assignment and motion planning actions"""
        super().setup_scheduling()

        # Attach task assignment action
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.LOGIC].addAction(self._action_decentralized_task_assignment)

        # Attach motion planning action
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.LOGIC].addAction(self._action_motion_planning)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _action_decentralized_task_assignment(self):
        """Decentralized task assignment action (greedy nearest).""" #TODO: check here if only for this strategy
        if self.ta_cont.assigned_task is not None or not self.tai.assignment_pending:
            return  # Already have task

        # Tasks come from local world representation (updated by environment)
        available_tasks = self.lwr_cont.tasks if self.lwr_cont else {}
        if not available_tasks:
            return  # No tasks available
        
        self.logger.info('Doing decentralized task assignment')

        min_distance = float('inf')
        nearest_task = None

        for task_container in available_tasks.values():
            distance = self.tai.distance_fun(self.container, task_container)
            if distance < min_distance:
                min_distance = distance
                nearest_task = task_container

        if nearest_task:
            self.ta_cont.state.assigned_task = nearest_task
            self.tai.assignment_pending = False
            self.logger.info(f"Agent {self.agent_id} assigned task {nearest_task.object_id} (distance: {min_distance:.2f})")

    def _action_motion_planning(self):
        """Motion planning action - creates phase for assigned task."""
         # TODO: give the option here to not use current as starting position
        if self.mp_cont.start_planning is not None:
            phase_key = self.mp_cont.start_planning
            task = self.assigned_task

            if task is None:
                self.logger.warning(f'MP planning requested for phase "{phase_key}", but no assigned task')
                self.mp_cont.start_planning = None
                return

            self.logger.info(f"Planning motion to task {task.object_id} at {task.configuration} (phase: {phase_key})")

            # Call motion planner (this adds the phase to runner)
            self.mpi.plan_motion(
                phase_key=phase_key,
                goal_task=task
            )

            # Activate the phase if planning succeeded
            if phase_key in self.runner._phases:
                self.runner.activate_phase(phase_key)
                self.logger.info(f"Activated motion phase {phase_key}")

            # Reset the planning flag
            self.mp_cont.start_planning = None

    # ------------------------------------------------------------------
    # MODULE related functions
    # ------------------------------------------------------------------

    @property
    def ta_cont(self):
        return self.tai.ta_cont
    
    @property
    def mp_cont(self):
        return self.mpi.mp_cont

    @property
    def assigned_task(self):
        """Link to the task assigned by TA module."""
        return self.tai.ta_cont.assigned_task

    @assigned_task.setter
    def assigned_task(self, value):
        """Set assigned task and trigger motion planning."""
        self.tai.ta_cont.assigned_task = value





def main():
    import time
    from master_thesis.general.general_simulation import FRODO_general_Simulation
    from master_thesis.general.general_task import GeneralTask

    # Initialize Sim
    sim = FRODO_general_Simulation()
    sim.init()

    # Initialize Agent
    agent = FRODOUniversalAgent(agent_id = 'frodo01', env_container=sim.environment.environment_container ,start_config= (0.0,0.0,0.0))
    sim.add_agent(agent)

    # Initialize Task
    task = GeneralTask(id='mock_task', x = 2, y = 2, psi = 0)

    # Add task to simulation - it will be automatically visible to agent via lwr_cont
    sim.add_task(task)

    sim.start()

    

    while True:
        time.sleep(10)
if __name__ == "__main__":
    main()

