from abc import ABC, abstractmethod
from typing import Any

from master_thesis.containers.general_containers.agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.task_container import TaskContainer
from master_thesis.containers.module_containers.ta_containers.ta_container_sim import SimTAContainer
from core.utils.logging_utils import Logger


class BaseStrategy(ABC):
    """Base class for task assignment strategies.

    Subclasses implement either centralized or decentralized assignment.
    Split into CentralizedStrategyABC and DecentralizedStrategyABC.
    """

    def __init__(self) -> None:
        super().__init__()

    def solve(self, agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> SimTAContainer | None:
        return None

    @abstractmethod
    def run(self, result_cont: Any, agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> Any:
        """Run the assignment strategy. Returns the assignment context container with results.

        Args:
            agent_containers: Dict of agent containers by object_id
            task_containers: Dict of task containers by object_id
            logger: Optional logger

        Returns:
            CentralizedAssignmentContainer for centralized strategies,
            dict[agent_id, DecentralizedAssignmentContainer] for decentralized strategies
        """
        ...