import numpy as np
from typing import List, Type, Callable
from numpy.typing import NDArray

from extensions.simulation.src import core as core

from master_thesis.task_assignment.task_objects import Task
from master_thesis.general.general_agents import FRODOGeneralAgent


class AssignmentAgentModule():
    """Interface for assignment agents. Handles decentralized assignments"""
    agent_id: str   # Unique identifier for the agent

    def __init__(self, agent_id, logger, get_state_fun: Callable[[], core.spaces.State]):
        
        self.agent_id = agent_id
        self._available_tasks = []
        self._assigned_tasks = []
        self.logger = logger
        self._get_state_fun = get_state_fun 
        # TODO: Use metric, e.g. dubins distance which accounts for turning radius
        self.cost_function = self.euclidean_distance_cost_2d  # set the cost function

    def calc_task_cost(self, task_configuration) -> np.floating:

        return self.cost_function(task_configuration=task_configuration)
    
    # TODO: Implement dubins cost!
    def euclidean_distance_cost_2d(self, task_configuration) -> np.floating: # TODO: implement dubins cost
        # extract x and y from the agent
        agent_state = self._get_state_fun()
        agent_position = np.array((agent_state.x, agent_state.y))

        # extract x and y from the task
        task_position = np.array([task_configuration[0]["x"], task_configuration[0]["y"]])

        # compute euclidean distance 
        distance = np.linalg.norm(agent_position - task_position)

        return distance
    
    def add_tasks(self, tasks: tuple[Task,...]) -> None:
        # Add only tasks with unique IDs to the available_tasks list
        existing_ids = {task.id for task in self._available_tasks}
        new_tasks = [task for task in tasks if task.object_id not in existing_ids]
        duplicated_ids = [task.object_id for task in tasks if task.object_id in existing_ids]
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

        # add assignment module
        self.asi = AssignmentAgentModule(
            agent_id=agent_id,
            logger=self.logger,
            get_state_fun=self._get_state
        )