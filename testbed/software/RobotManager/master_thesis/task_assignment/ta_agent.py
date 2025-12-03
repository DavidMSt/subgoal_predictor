import numpy as np
from typing import List, Type, Callable
from numpy.typing import NDArray

from extensions.simulation.src import core as core

from master_thesis.task_assignment.task_objects import Task
from master_thesis.general.general_agents import FRODOGeneralAgent
from master_thesis.containers.ta_container import AgentTAContainer
from master_thesis.containers.agent_containers import FRODOAgentContainer
from master_thesis.containers.environment_containers import EnvironmentContainer

class DistanceCalculator:
    """
    Selects a distance function based on a string key and exposes it 
    via .measure(agent_container, task_container).
    """

    # registry of available metrics
    _REGISTRY = {
        "euclidean": "_euclidean_distance_2d",
        "dubins": "_dubins_distance",
    }

    def __init__(self, metric: str):
        metric = metric.lower()
        if metric not in self._REGISTRY:
            raise ValueError(f"Unknown distance metric '{metric}'.")

        # Dynamically bind the correct function for later calls
        method_name = self._REGISTRY[metric]
        self.measure = getattr(self, method_name)

    # ---------------- distance functions ---------------- #

    def _euclidean_distance_2d(self, agent_container, task_container) -> float:
        # extract agent (dynamic) position
        ax, ay = agent_container.state.x, agent_container.state.y

        # extract task (static) position
        tx, ty = task_container.config.x, task_container.config.y

        return float(np.hypot(ax - tx, ay - ty))

    def _dubins_distance(self, agent_container, task_container) -> float:
        # placeholder
        raise NotImplementedError("Dubins distance not implemented yet")
    

class TAAgentModule():
    """Interface for assignment agents. Handles decentralized assignments"""
    agent_id: str   # Unique identifier for the agent
    task_assignment_container: AgentTAContainer

    def __init__(self, agent_id: str, agent_container, ta_container: AgentTAContainer, logger, get_state_fun: Callable[[], core.spaces.State]):

        self.agent_id = agent_id
        self.task_assignment_container = ta_container
        self.agent_container = agent_container
        self.logger = logger
        self._get_state_fun = get_state_fun
        # TODO: Use metric, e.g. dubins distance which accounts for turning radius
        self.distance_fun = DistanceCalculator(self.task_assignment_container.distance_metric).measure  # set the cost function
    
    def add_tasks(self, tasks: tuple[Task,...]) -> None:
        # Add only tasks with unique IDs to the available_tasks list
        existing_ids = set(self.task_assignment_container.available_tasks)
        new_task_ids = [task.object_id for task in tasks if task.object_id not in existing_ids]
        duplicated_ids = [task.object_id for task in tasks if task.object_id in existing_ids]
        if duplicated_ids:
            self.logger.warning(f'Detected duplicated tasks with IDs: {duplicated_ids}, keeping only one instance')
        self.task_assignment_container.available_tasks.extend(new_task_ids)

    def clear_tasks(self):
        self.task_assignment_container.available_tasks.clear()

    def clear_assigned_tasks(self):
        self.task_assignment_container.assigned_tasks.clear()

    def compute_task_cost_vector(self, tasks: tuple[Task, ...]) -> list[np.floating]:

        task_configurations = self.extract_task_configurations(tasks)
        cost_vector = [self.distance_fun(self.agent_container, configuration) for configuration in task_configurations]
        return cost_vector

    # def extract_task_configurations(self, tasks: tuple[Task, ...]) -> list[core.spaces.State]:
    #     """
    #     Extracts the local positions of agents or tasks from a list of objects.
    #     """
    #     configurations = []
    #     for task in tasks:
    #         configurations.append(task.configuration)
    #     return configurations
    
    def assign_task(self, task_id: str) -> None:
        """Assign a task to this agent (centralized assignment)"""
        self.task_assignment_container.assigned_tasks.append(task_id)
        if self.task_assignment_container.current_task_id is None:
            self.task_assignment_container.current_task_id = task_id
        self.logger.info(f"Agent {self.agent_id} assigned task {task_id}")

    def get_current_task_goal(self, tasks_dict: dict) -> tuple[float, float] | None:
        """Get goal position from current task"""
        if self.task_assignment_container.current_task_id is None:
            return None
        task = tasks_dict[self.task_assignment_container.current_task_id]
        return tuple(task.position)

    def mark_task_complete(self):
        """Mark current task as complete, move to next"""
        if self.task_assignment_container.current_task_id:
            self.logger.info(f"Agent {self.agent_id}: Task {self.task_assignment_container.current_task_id} completed")
            self.task_assignment_container.tasks_completed += 1
            self.task_assignment_container.current_task_id = None

            # Move to next task in queue if available
            if len(self.task_assignment_container.assigned_tasks) > 0:
                self.task_assignment_container.current_task_id = self.task_assignment_container.assigned_tasks[0]
                self.task_assignment_container.assigned_tasks.pop(0)
                self.logger.info(f"Agent {self.agent_id}: Starting next task {self.task_assignment_container.current_task_id}")

class FRODO_AssignmentAgent(FRODOGeneralAgent):

    def __init__(
        self,
        agent_id: str,
        start_config: tuple[float, float, float],
        agent_config=None,
        runner=None,
        Ts=None,
        **kwargs
    ):
        super().__init__(
            agent_id=agent_id,
            start_config=start_config,
            agent_config=agent_config,
            Ts=Ts,
        )

        self.runner = runner

        print(self.state)

        # Create task container
        from testbed.software.RobotManager.master_thesis.general.containers.ta_container import AgentTaskConfig, AgentTaskState
        task_container = AgentTAContainer(
            config=AgentTaskConfig(),
            state=AgentTaskState()
        )

        # add assignment module
        self.asi = TAAgentModule(
            agent_id=agent_id,
            ta_container=task_container,
            logger=self.logger,
            get_state_fun=self._get_state
        )