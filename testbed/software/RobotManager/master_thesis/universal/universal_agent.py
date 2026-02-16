from abc import ABC, abstractmethod
from typing import List

from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS

from master_thesis.general.general_agent import FRODOGeneralAgent, FRODO_Agent_Config
from master_thesis.modules.task_assignment.ta_agent_module import TAAgentModule

# Pipeline abstractions
from master_thesis.modules.motion_planning.path_planner_base import PathPlannerBase, PlanResult
from master_thesis.modules.execution.motion_executor_base import MotionExecutorBase
from master_thesis.modules.motion_planning.subgoal_manager import SubgoalManager

# Containers
from master_thesis.containers.general_containers.environment_container import EnvironmentContainer
from master_thesis.containers.module_containers.ta_containers.ta_container_agent import AgentTAContainer, AgentTAConfig, AgentTAState
from master_thesis.containers.module_containers.mp_containers.mp_planner_container import AgentMPPlannerContainer
from master_thesis.containers.module_containers.mp_containers.mp_phase_container import MPPhaseContainer
from master_thesis.containers.module_containers.exe_containers.exe_container import AgentExeContainer
from master_thesis.containers.general_containers.task_container import TaskContainer
from master_thesis.containers.general_containers.local_world_container import LocalWorldContainer

import master_thesis.modules.task_assignment.strategies.centralized_strategies


class FRODOUniversalAgent(FRODOGeneralAgent, ABC):
    """
    Abstract base agent with swappable planning pipeline: TA -> Planner -> Executor.

    Subclasses must override ``_build_pipeline()`` to provide a concrete
    planner/executor combination:

      - FRODOOfflineAgent     → OMPL + Trajectory Playback
      - FRODOReactiveAgent    → Direct Goal + MPPI
      - FRODORLAgent          → RL Subgoal Predictor + MPPI
    """
    tam: TAAgentModule
    planner: PathPlannerBase
    executor: MotionExecutorBase
    sgm: SubgoalManager

    def __init__(self, env_container, agent_id: str, Ts=0.1, start_config=(0.0,0.0,0.0),
                 color: tuple[float, float, float] = (1.0, 1.0, 1.0), log_level: str = 'INFO') -> None:
        super().__init__(agent_id=agent_id, Ts=Ts, start_config=start_config, color=color, log_level=log_level)

        # TODO: Use bilbolab code for this if possible
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

        # Build planner + executor (overridden by subclasses)
        self.planner, self.executor = self._build_pipeline()

        # SubgoalManager coordinates planner <-> executor
        self.sgm = SubgoalManager(
            planner=self.planner,
            executor=self.executor,
            logger=self.logger,
        )

    @abstractmethod
    def _build_pipeline(self) -> tuple[PathPlannerBase, MotionExecutorBase]:
        """Build planner + executor pair."""
        ...

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def setup_scheduling(self):
        """Override to add task assignment, planning, and execution actions."""
        super().setup_scheduling()

        # LOGIC: task assignment → planning trigger → replan tick
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.LOGIC].addAction(self._action_decentralized_task_assignment)
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.LOGIC].addAction(self._action_planning)
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.LOGIC].addAction(self._action_planning_tick)

        # INPUT: get controls from executor
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.INPUT].addAction(self._action_executor_step)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _action_decentralized_task_assignment(self):
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

            # Notify SubgoalManager
            self.sgm.assign_task(chosen_task)

            # Write decision to shared dict (for simulation to detect completion and conflicts)
            local_decisions = self.ta_cont.state.local_decisions
            if local_decisions is not None:
                local_decisions[self.agent_id] = chosen_task.object_id
                self.logger.debug(f"Wrote decision to local_decisions: {self.agent_id} -> {chosen_task.object_id}")

            self.logger.info(f"Agent {self.agent_id} assigned task {chosen_task.object_id}")

    def _action_planning(self):
        """Triggered by sim.start_mp() setting a flag. Runs planner once."""
        if self.sgm.start_planning_flag is not None:
            phase_key = self.sgm.start_planning_flag

            task = self.assigned_task
            if task is None:
                self.logger.warning(f'Planning requested (phase "{phase_key}"), but no assigned task')
                self.sgm.start_planning_flag = None
                return

            self.logger.info(f"Planning motion to task {task.object_id} at {task.configuration} (phase: {phase_key})")
            self.sgm.start_planning(phase_key)
            self.sgm.start_planning_flag = None

    def _action_planning_tick(self):
        """Every tick: check replan for reactive modes."""
        self.sgm.tick()

    def _action_executor_step(self):
        """Get control from executor."""
        u = self.executor.step()
        self.input.v = float(u[0])
        self.input.psi_dot = float(u[1])

    # ------------------------------------------------------------------
    # MODULE related functions
    # ------------------------------------------------------------------

    # ---------- Task Assignment ----------
    @property
    def ta_cont(self):
        return self.tam.ta_container

    @property
    def assigned_task(self)-> TaskContainer | None:
        """Link to the task assigned by TA module."""
        return self.tam.ta_container.assigned_task

    @assigned_task.setter
    def assigned_task(self, task: TaskContainer):
        """Set assigned task and notify SubgoalManager."""
        assert isinstance(task, TaskContainer)
        self.tam.ta_container.assigned_task = task
        self.sgm.assign_task(task)

    # ---------- Motion Planning ----------
    @property
    def mp_cont(self) -> AgentMPPlannerContainer | None:
        """Expose OMPL planner container (only available in OFFLINE mode)."""
        from master_thesis.modules.motion_planning.ompl_trajectory_planner import OMPLTrajectoryPlanner
        if isinstance(self.planner, OMPLTrajectoryPlanner):
            return self.planner.planner_cont
        return None

    @property
    def planned_phases(self):
        from master_thesis.modules.motion_planning.ompl_trajectory_planner import OMPLTrajectoryPlanner
        if isinstance(self.planner, OMPLTrajectoryPlanner):
            return self.planner.planner_cont.phases
        return {}

    # ---------- Phase Execution ----------

    @property
    def exe_cont(self) -> AgentExeContainer | None:
        """Expose execution container (only available in OFFLINE mode)."""
        from master_thesis.modules.execution.trajectory_executor import TrajectoryExecutor
        if isinstance(self.executor, TrajectoryExecutor):
            return self.executor.exe_cont
        return None

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
