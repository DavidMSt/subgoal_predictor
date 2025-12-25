from typing import List

from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS

from master_thesis.general.general_agent import FRODOGeneralAgent, FRODO_Agent_Config
from master_thesis.motion_planning.mp_agent_module import MPAgentModule
from master_thesis.task_assignment.ta_agent_module import TAAgentModule
from master_thesis.execution.exe_agent_module import EXEAgentModule

from master_thesis.containers.general_containers.environment_container import EnvironmentContainer
from master_thesis.containers.module_containers.ta_containers.ta_container_agent import AgentTAContainer, AgentTAConfig, AgentTAState
from master_thesis.containers.module_containers.mp_containers.mp_planner_container import AgentMPPlannerContainer
from master_thesis.containers.module_containers.mp_containers.mp_phase_container import MPPhaseContainer
from master_thesis.containers.module_containers.exe_containers.exe_container import AgentExeContainer

import master_thesis.task_assignment.strategies.centralized_strategies 

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
        mp_container = AgentMPPlannerContainer()
        exe_container = AgentExeContainer()
     
        # ------------------------------------------------------------------
        # MODULES
        # ------------------------------------------------------------------

        # MPAgent module
        self.mpi = MPAgentModule(
            agent_cont=self.container, 
            env_container=env_container, 
            logger=self.logger)

        # TAAgent module
        self.tai = TAAgentModule(
            agent_id=agent_id,
            agent_container = self.container,
            lwr_cont = self.lwr_cont,
            logger=self.logger,
        )

        self.exi = EXEAgentModule(
            agent_cont= self.container,
            logger = self.logger,
        ) # TODO

    def setup_scheduling(self):
        """Override to add task assignment, motion planning, and execution actions"""
        super().setup_scheduling()

        # Attach task assignment action
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.LOGIC].addAction(self._action_decentralized_task_assignment)

        # Attach motion planning action
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.LOGIC].addAction(self._action_motion_planning)

        # Attach execution transfer action (moves planned phases to execution)
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.LOGIC].addAction(self._action_execution)

        # Attach input function (provides control inputs from execution module)
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.INPUT].addAction(self._input_function)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _action_decentralized_task_assignment(self):
        """Decentralized task assignment action (greedy nearest).""" #TODO: check here if only for this strategy
        if self.ta_cont.assigned_task is not None or not self.tai.assignment_pending:
            return  # Already have task

        # # Tasks come from local world representation (updated by environment)
        # available_tasks = self.lwr_cont.tasks if self.lwr_cont else {}
        # if not available_tasks:
        #     return  # No tasks available
        
        self.logger.info('Doing decentralized task assignment')

        self.tai.assign_task()

        # min_distance = float('inf')
        # nearest_task = None

        # for task_container in available_tasks.values():
        #     distance = self.tai.distance_fun(self.container, task_container)
        #     if distance < min_distance:
        #         min_distance = distance
        #         nearest_task = task_container

        # if nearest_task:
        #     self.ta_cont.assigned_task = nearest_task
        #     self.tai.assignment_pending = False
        #     self.logger.info(f"Agent {self.agent_id} assigned task {nearest_task.object_id} (distance: {min_distance:.2f})")
        # TODO: put here the writing to the sim central dict 

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

            # Reset the planning flag
            self.mp_cont.start_planning = None

    def _action_execution(self):
        if not self.planned_phases or not self.exe_cont.start_execution:
            return

        # Get list of phase names to avoid dict modification during iteration
        phase_names = list(self.planned_phases.keys())
        
        for phase_name in phase_names:
            if phase_name not in self.exi.phases:
                phase_container = self.planned_phases[phase_name]
                
                # Transfer to execution
                self.exi.add_phase(phase_name, phase_container)

                # Remove from MP module (phase has been transferred)
                del self.mp_cont.phases[phase_name]
                
                self.logger.info(f"Phase '{phase_name}' transferred to execution module")
                
                # Activate
                self.exi.activate_phase(phase_name)
                

                
                break


    def _input_function(self):
        """Override parent to use execution module for control inputs."""
        u = self.exi.step()
        self.input.v = float(u[0])
        self.input.psi_dot = float(u[1])

    # ------------------------------------------------------------------
    # MODULE related functions
    # ------------------------------------------------------------------

    # ---------- Task Assignment ----------
    @property
    def ta_cont(self):
        return self.tai.task_containers
    
    @property
    def assigned_task(self):
        """Link to the task assigned by TA module."""
        return self.tai.task_containers.assigned_task

    @assigned_task.setter
    def assigned_task(self, value):
        """Set assigned task and trigger motion planning."""
        self.tai.task_containers.assigned_task = value

    # ---------- Motion Planning ----------
    @property
    def mp_cont(self):
        return self.mpi.planner_cont
    
    @property
    def planned_phases(self):
        return self.mpi.planner_cont.phases
    
    @planned_phases.setter #TODO: write access could be removed here? 
    def planned_phases(self, name: str, phase: MPPhaseContainer):
        self.mpi.planner_cont.phases[name] = phase
    
    # ---------- Phase Execution ----------
    
    @property
    def exe_cont(self):
        return self.exi.exe_cont



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

