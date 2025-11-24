import numpy as np
from typing import List, Type, Callable
from numpy.typing import NDArray

from extensions.simulation.src import core as core

from master_thesis.task_assignment.task_objects import Task
from master_thesis.general.general_agents import FRODOGeneralAgent


class AssignmentAgentModule():
    """Interface for assignment agents. Handles decentralized assignments"""
    agent_id: str   # Unique identifier for the agent

    def __init__(self, Ts, agent_id, logger, get_configuration: Callable[[], core.spaces.State]):
        
        self.agent_id = agent_id
        self._available_tasks = []
        self._assigned_tasks = []
        self.logger = logger
        self._get_configuration = get_configuration 
        # TODO: Use metric, e.g. dubins distance which accounts for turning radius
        self.cost_function = self.euclidean_distance_cost_2d  # set the cost function

    def calc_task_cost(self, task_configuration) -> np.floating:

        return self.cost_function(task_configuration=task_configuration)
    
    def euclidean_distance_cost_2d(self, task_configuration) -> np.floating: # TODO: implement dubins cost
        # extract x and y from the agent
        agent_configuration = self._get_configuration()
        agent_position = np.array([agent_configuration[0]["x"], agent_configuration[0]["y"]])

        # extract x and y from the task
        task_position = np.array([task_configuration[0]["x"], task_configuration[0]["y"]])

        # compute euclidean distance 
        distance = np.linalg.norm(agent_position - task_position)

        return distance
    
    def add_tasks(self, tasks: tuple[Task,...]) -> None:
        # Add only tasks with unique IDs to the available_tasks list
        existing_ids = {task.id for task in self._available_tasks}
        new_tasks = [task for task in tasks if task.id not in existing_ids]
        duplicated_ids = [task.id for task in tasks if task.id in existing_ids]
        if duplicated_ids:
            self.logger.warning(f'Detected duplicated tasks with IDs: {duplicated_ids}, keeping only one instance')
        self._available_tasks += new_tasks

    def clear_tasks(self):
        self._available_tasks.clear()

    def clear_assigned_tasks(self):
        self._assigned_tasks.clear()

    def compute_task_cost_vector(self, tasks: tuple[Task, ...]) -> list[np.floating]:

        task_configurations = self.extract_task_configurations(tasks)
        cost_vector = [self.calc_task_cost(task_configuration=configuration) for configuration in task_configurations]
        return cost_vector

    def extract_task_configurations(self, tasks: tuple[Task, ...]) -> list[core.spaces.State]:
        """
        Extracts the local positions of agents or tasks from a list of objects.
        """
        configurations = []
        for task in tasks:
            configurations.append(task.configuration)
        return configurations
    
    def assign_task(self, task: Task)-> None:
        self._assigned_tasks.append(task)



class FRODO_AssignmentAgent(FRODOGeneralAgent):
    def __init__(self, start_config: List[float], fov_deg=360, view_range=1.5, runner: bool = True, *args, **kwargs) -> None:
        super().__init__(start_config, fov_deg, view_range, runner, *args, **kwargs)
        self.asi = AssignmentAgentModule(self.Ts, self.id, self.logger, self.getConfiguration)



