from typing import List

from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS

from master_thesis.general.general_agents import FRODOGeneralAgent, FRODO_Agent_Config
from master_thesis.motion_planning.mp_agent_module import MPAgentModule
from master_thesis.task_assignment.ta_agent_module import TAAgentModule

from master_thesis.containers.general_containers.environment_container import EnvironmentContainer
from master_thesis.containers.module_containers.ta_container import AgentTAContainer, AgentTAConfig, AgentTAState
from master_thesis.containers.module_containers.mp_container import AgentMPContainer
from master_thesis.containers.module_containers.exe_container import ExecutionContainer


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

        self.exe = ... # TODO

    def setup_scheduling(self):
        """Override to add task assignment and motion planning actions"""
        super().setup_scheduling()

        # Attach task assignment action
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.LOGIC].addAction(self._action_task_assignment)

        # Attach motion planning action
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.LOGIC].addAction(self._action_motion_planning)

    def _action_task_assignment(self):
        """Decentralized task assignment action (greedy nearest)."""
        if self.tai.ta_container.state.assigned_task is not None:
            return  # Already have task
        if not self.tai.assignment_pending:
            return  # No assignment requested

        # Greedy assignment: select nearest available task
        available_tasks = self.tai.ta_container.state.available_tasks
        if not available_tasks:
            return  # No tasks available

        min_distance = float('inf')
        nearest_task = None

        for task_container in available_tasks:
            distance = self.tai.distance_fun(self.container, task_container)
            if distance < min_distance:
                min_distance = distance
                nearest_task = task_container

        if nearest_task:
            self.tai.ta_container.state.assigned_task = nearest_task
            self.tai.assignment_pending = False
            self.logger.info(f"Agent {self.agent_id} assigned task {nearest_task.object_id} (distance: {min_distance:.2f})")

    def _action_motion_planning(self):
        """Motion planning action - creates phase for assigned task."""
        if self.tai.ta_container.state.assigned_task is None:
            return  # No task to plan for
        if self.runner.active != "idle":
            return  # Already executing a phase

        # Plan motion to assigned task
        task = self.tai.ta_container.state.assigned_task
        start_config = (self.state.x, self.state.y, self.state.psi)
        goal_config = (task.x, task.y, task.psi)

        phase_key = f"task_{task.object_id}"

        self.logger.info(f"Planning motion from {start_config} to task {task.object_id} at {goal_config}")

        # Call motion planner (this adds the phase to runner)
        self.mpi.plan_motion(
            phase_key=phase_key,
            start_config=start_config,
            goal_config=goal_config
        )

        # Activate the phase if planning succeeded
        if phase_key in self.runner._phases:
            self.runner.activate_phase(phase_key)
            self.logger.info(f"Activated motion phase {phase_key}")



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

