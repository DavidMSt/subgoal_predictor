import numpy as np
from typing import Callable

from simulation import core as core
from core.utils.logging_utils import Logger

from master_thesis.general.general_task import GeneralTask
from master_thesis.general.general_agent import FRODOGeneralAgent

from master_thesis.containers.general_containers.frodo_agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.task_container import TaskContainer
from master_thesis.containers.general_containers.local_world_container import LocalWorldContainer
from master_thesis.containers.module_containers.ta_containers.ta_container_agent import AgentTAContainer, AgentTAConfig, AgentTAState
from master_thesis.modules.task_assignment.strategies.decentralized_strategies import DecentralizedStrategyABC
from master_thesis.modules.task_assignment.strategies.strategy_registry import StrategyRegistry


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

    def __init__(self, agent_id: str, 
                 agent_container: FRODOAgentContainer, 
                 lwr_cont: LocalWorldContainer| None,
                 logger: Logger,
                 comm_func: Callable | None):

        # Set ID of corresponding agent
        self.agent_id = agent_id

        # Use same logger as the agent
        self.logger = logger

        # Own container of the agent
        self.agent_cont = agent_container

        # Get local world representation (visible tasks, agents and obstacles)
        self.lwr = lwr_cont

        self.ta_container = AgentTAContainer(logger= logger)

        # TODO: Use metric, e.g. dubins distance which accounts for turning radius - also make this more elegant?
        self.distance_fun = DistanceCalculator(self.ta_container.config.distance_metric).measure  # set the cost function

        # communication related things
        self.comm_func = comm_func
        self.agent_cont.comm_buffer["edge_embeddings"] = {}
        self.agent_cont.comm_buffer["assigned_task"] = {}

    def perform_task_assignment(self) -> TaskContainer | None:
        """
        Execute task assignment using strategy from container state. 
        Will always be decentralized assignment, since central versions are computed at simulation level.

        Returns:
            TaskContainer: Chosen task, or None if no assignment made
        """
        assert isinstance(self.lwr, LocalWorldContainer)

        # Get strategy from state (set by simulation)
        strategy_name = self.ta_container.state.current_strategy
        if not strategy_name:
            self.logger.warning("No strategy set in ta_container.state.current_strategy")
            return None

        # Get strategy instance from registry
        strategy = StrategyRegistry.get_decentralized(strategy_name)

        # Get live data from local world
        visible_tasks = self.lwr.state.tasks
        visible_neighbors = self.lwr.state.neighbors

        # Execute strategy
        chosen_task = strategy.solve(
            agent_container=self.agent_cont,
            task_containers=visible_tasks,
            visible_agent_containers=visible_neighbors,
            logger=self.logger,
            comm_func = self.comm_func
        )

        return chosen_task

    def clear_assigned_task(self):
        """Clear the currently assigned task."""
        self.ta_container.state._assigned_task = None

    def compute_task_cost_vector(self, tasks: tuple[GeneralTask, ...]) -> list[np.floating]:
        """Compute cost vector for a list of tasks based on distance from agent."""
        cost_vector = [self.distance_fun(self.agent_cont, task.container) for task in tasks]
        return cost_vector
    
    @property
    def assignment_pending(self) -> bool:
        return self.ta_container.assignment_pending
    
    @assignment_pending.setter
    def assignment_pending(self, value: bool = False) -> None:
        self.ta_container.assignment_pending = value
        