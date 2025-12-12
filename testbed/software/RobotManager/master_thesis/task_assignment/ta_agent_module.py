import numpy as np

from extensions.simulation.src import core as core

from master_thesis.general.general_task import GeneralTask
from master_thesis.general.general_agent import FRODOGeneralAgent
from master_thesis.containers.module_containers.ta_containers.ta_container_agent import AgentTAContainer
from master_thesis.containers.module_containers.ta_containers.ta_container_agent import AgentTAConfig, AgentTAState

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
        ax, ay = agent_container.x, agent_container.y

        # extract task (static) position
        tx, ty = task_container.x, task_container.y

        return float(np.hypot(ax - tx, ay - ty))

    def _dubins_distance(self, agent_container, task_container) -> float:
        # placeholder
        raise NotImplementedError("Dubins distance not implemented yet")
    

class TAAgentModule():
    """Interface for assignment agents. Handles decentralized assignments"""
    agent_id: str   # Unique identifier for the agent
    ta_cont: AgentTAContainer

    def __init__(self, agent_id: str, agent_container, ta_container: AgentTAContainer, logger):

        self.agent_id = agent_id
        self.ta_cont = ta_container
        self.agent_cont = agent_container
        self.logger = logger

        # TODO: Use metric, e.g. dubins distance which accounts for turning radius
        self.distance_fun = DistanceCalculator(self.ta_cont.distance_metric).measure  # set the cost function

    # NOTE: Available tasks now come from agent.lwr_cont.tasks (updated by environment)
    # No need to manually add/clear tasks - they're managed by environment sensing updates

    def clear_assigned_task(self):
        """Clear the currently assigned task."""
        self.ta_cont.state.assigned_task = None

    def compute_task_cost_vector(self, tasks: tuple[GeneralTask, ...]) -> list[np.floating]:
        """Compute cost vector for a list of tasks based on distance from agent."""
        cost_vector = [self.distance_fun(self.agent_cont, task.container) for task in tasks]
        return cost_vector
    
    def assign_task(self, task_id: str) -> None:
        """Assign a task to this agent (centralized assignment)"""
        self.ta_cont.assigned_tasks.append(task_id)
        if self.ta_cont.current_task_id is None:
            self.ta_cont.current_task_id = task_id
        self.logger.info(f"Agent {self.agent_id} assigned task {task_id}")

    def get_current_task_goal(self, tasks_dict: dict) -> tuple[float, float] | None:
        """Get goal position from current task"""
        if self.ta_cont.current_task_id is None:
            return None
        task = tasks_dict[self.ta_cont.current_task_id]
        return (task.container.x, task.container.y)

    def mark_task_complete(self):
        """Mark current task as complete, move to next"""
        if self.ta_cont.current_task_id:
            self.logger.info(f"Agent {self.agent_id}: Task {self.ta_cont.current_task_id} completed")
            self.ta_cont.tasks_completed += 1
            self.ta_cont.current_task_id = None

            # Move to next task in queue if available
            if len(self.ta_cont.assigned_tasks) > 0:
                self.ta_cont.current_task_id = self.ta_cont.assigned_tasks[0]
                self.ta_cont.assigned_tasks.pop(0)
                self.logger.info(f"Agent {self.agent_id}: Starting next task {self.ta_cont.current_task_id}")

    @property
    def assignment_pending(self) -> bool:
        return self.ta_cont.assignment_pending
    
    @assignment_pending.setter
    def assignment_pending(self, value: bool = False) -> None:
        self.ta_cont.assignment_pending = value
        