# 3rd party
from typing import Optional

# bilbolab
from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS

# master thesis
from master_thesis.general.general_agent import FRODOGeneralAgent
from master_thesis.modules.task_assignment.ta_agent_module import TAAgentModule
from master_thesis.modules.local_control.local_control_module import LocalControlModule
from master_thesis.modules.local_control.local_controller import LocalController
from master_thesis.modules.local_control.mppi_controller import MPPIController, MPPIConfig

from master_thesis.containers.general_containers.environment_container import EnvironmentContainer
from master_thesis.containers.module_containers.ta_containers.ta_container_agent import AgentTAContainer
from master_thesis.containers.general_containers.task_container import TaskContainer
from master_thesis.containers.general_containers.local_world_container import LocalWorldContainer


class FRODOReactiveAgent(FRODOGeneralAgent):
    """
    Agent with reactive/online control pipeline: TA -> LocalControl (MPPI/MPC).

    This agent computes controls online at each timestep via a reactive controller
    (e.g., MPPI, MPC, ORCA). Good for dynamic environments where replanning is needed.

    Unlike OfflinePlanAgent which pre-computes full trajectories via OMPL,
    this agent reacts in real-time to the current state and environment.
    """
    tam: TAAgentModule
    lcm: LocalControlModule

    def __init__(
        self,
        env_container,
        agent_id: str,
        Ts: float = 0.1,
        start_config: tuple[float, float, float] = (0.0, 0.0, 0.0),
        color: tuple[float, float, float] = (1.0, 1.0, 1.0),
        controller: Optional[LocalController] = None,
        log_level: str = 'INFO'
    ) -> None:
        """
        Args:
            env_container: Environment container
            agent_id: Unique agent identifier
            Ts: Timestep
            start_config: Initial (x, y, psi)
            color: RGB color
            controller: Local controller instance (defaults to MPPI)
            log_level: Logging level
        """
        super().__init__(agent_id=agent_id, Ts=Ts, start_config=start_config, color=color, log_level=log_level)

        # Create default MPPI controller if none provided
        if controller is None:
            config = MPPIConfig(
                dt=Ts,
                horizon=30,
                n_samples=100,
                control_limits=((-1.0, 1.0), (-2.0, 2.0)),  # v, psi_dot limits
            )
            controller = MPPIController(config)

        # TODO: Use bilbolab code for this if possible
        print('this is the container', self.container)

        self.container.comm_buffer["task_costs"] = {}
        self.container.comm_buffer["assigned_task"] = {}

        # ------------------------------------------------------------------
        # MODULES
        # ------------------------------------------------------------------

        # TAAgent module (lwr_cont will be set by simulation after agent is added)
        self.tam = TAAgentModule(
            agent_id=agent_id,
            agent_container=self.container,
            lwr_cont=None,  # Will be set after agent is added to simulation
            logger=self.logger,
            comm_func= self.comm_func
        )

        # Local Control module (replaces MP + EXE)
        self.lcm = LocalControlModule(
            agent_cont=self.container,
            controller=controller,
            logger=self.logger,
        )

    def setup_scheduling(self):
        """Override to add task assignment and reactive control actions."""
        super().setup_scheduling()

        # Attach task assignment action
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.LOGIC].addAction(self._action_task_assignment)

        # Attach goal update action (transfers assigned task goal to controller)
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.LOGIC].addAction(self._action_update_goal)

        # Attach reactive control input (computes control at each step)
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.INPUT].addAction(self._action_reactive_control)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _action_task_assignment(self):
        """Decentralized task assignment action - uses strategy from container state."""
        if self.ta_cont.assigned_task is not None or not self.tam.assignment_pending:
            return  # Already have task or assignment not pending

        self.logger.info('Performing decentralized task assignment')

        # Execute strategy (set by simulation via container state)
        chosen_task = self.tam.perform_task_assignment()

        if chosen_task:
            # Assign task to agent
            self.ta_cont.assigned_task = chosen_task
            self.tam.assignment_pending = False

            # Also update task's assigned agent (bidirectional)
            chosen_task.assigned_agent = self.container

            # Write decision to shared dict (for simulation to detect completion and conflicts)
            local_decisions = self.ta_cont.state.local_decisions
            if local_decisions is not None:
                local_decisions[self.agent_id] = chosen_task.object_id
                self.logger.debug(f"Wrote decision to local_decisions: {self.agent_id} -> {chosen_task.object_id}")

            self.logger.info(f"Agent {self.agent_id} assigned task {chosen_task.object_id}")

    def _action_update_goal(self):
        """Update local controller goal when task is assigned."""
        task = self.assigned_task

        if task is None:
            return

        # Check if goal already set (avoid redundant updates)
        current_goal = self.lcm.current_goal
        task_goal = task.configuration

        if current_goal is not None:
            # Goal already set, check if reached
            if self.lcm.is_goal_reached():
                self.logger.info(f"Goal reached for task {task.object_id}")
                # Clear task assignment
                self.ta_cont.assigned_task = None
                self.lcm.clear_goal()
                self.tam.assignment_pending = True
            return

        # Set new goal from assigned task
        self.lcm.set_goal(task_goal)
        self.logger.info(f"Goal set to task {task.object_id} at {task_goal}")

    def _action_reactive_control(self):
        """Compute and apply reactive control at each timestep."""
        # Get control from local controller
        control = self.lcm.step(self.lwr_cont)

        # Apply control
        self.input.v = float(control[0])
        self.input.psi_dot = float(control[1])

    # ------------------------------------------------------------------
    # MODULE related functions
    # ------------------------------------------------------------------

    # ---------- Task Assignment ----------
    @property
    def ta_cont(self) -> AgentTAContainer:
        return self.tam.ta_container

    @property
    def assigned_task(self) -> TaskContainer | None:
        """Link to the task assigned by TA module."""
        return self.tam.ta_container.assigned_task

    @assigned_task.setter
    def assigned_task(self, task: TaskContainer):
        """Set assigned task."""
        assert isinstance(task, TaskContainer)
        self.tam.ta_container.assigned_task = task

    # ---------- Local Control ----------
    @property
    def controller(self) -> LocalController:
        """Access to the local controller."""
        return self.lcm.controller
    
    # TODO: is there an alternative from bilbolab? 
    def comm_func(self, payload: dict[str, dict]):
        assert isinstance(self.lwr_cont, LocalWorldContainer)

        self.container.comm_buffer["received_from"].clear()
        self.container.comm_buffer["task_costs"].clear()
        self.container.comm_buffer["assigned_task"].clear()

        for neighbor_cont in self.lwr_cont.neighbors.values():
            for topic, data in payload.items():
                if topic not in neighbor_cont.comm_buffer:
                    continue  # neighbor doesn't have this topic, skip

                if topic == "task_costs":
                    for task_id, cost in data.items():
                        if task_id in neighbor_cont.comm_buffer[topic]:
                            neighbor_cont.comm_buffer[topic][task_id].append(cost)
            
            neighbor_cont.comm_buffer["received_from"].append(self.container.agent_id)


def main():
    import time
    from master_thesis.general.general_simulation import FRODO_general_Simulation
    from master_thesis.general.general_task import GeneralTask

    # Initialize Sim
    sim = FRODO_general_Simulation()
    sim.init()

    # Initialize Agent with reactive control
    agent = FRODOReactiveAgent(
        agent_id='frodo01',
        env_container=sim.environment.environment_container,
        start_config=(0.0, 0.0, 0.0)
    )
    sim.add_agent(agent)

    # Initialize Task
    task = GeneralTask(id='mock_task', x=2, y=2, psi=0)

    # Add task to simulation
    sim.add_task(task)

    sim.start()

    while True:
        time.sleep(10)


if __name__ == "__main__":
    main()
