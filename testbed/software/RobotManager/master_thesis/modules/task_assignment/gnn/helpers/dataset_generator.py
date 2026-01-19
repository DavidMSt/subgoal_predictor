import torch
import math
import numpy as np
from typing import TYPE_CHECKING

from master_thesis.general.general_simulation import FRODO_general_Simulation
from master_thesis.modules.task_assignment.strategies.centralized_strategies import (
    RandomStrategyCent,
    HungarianStrategyCent,
    CentralizedStrategyABC
)
from master_thesis.modules.task_assignment.strategies.base_strategy import BaseStrategy
from master_thesis.containers.general_containers.agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.task_container import TaskContainer
from torch.utils.data import Dataset, DataLoader as TorchDataLoader
from core.utils.logging_utils import Logger

if TYPE_CHECKING:
    from master_thesis.general.general_agent import FRODOGeneralAgent
    from master_thesis.general.general_task import GeneralTask

class DataSetGenerator:
    """Generate training datasets for GNN-based task assignment.

    Works with the FRODO_general_Simulation to create scenes with agents and tasks,
    then uses centralized strategies (like Hungarian algorithm) to create optimal
    assignment labels for supervised learning.
    """

    def __init__(self, sim: FRODO_general_Simulation) -> None:
        """Initialize the dataset generator.

        Args:
            sim: A FRODO_general_Simulation instance (should be initialized but not started)
        """
        self.sim = sim
        self.index = 0
        self.logger = sim.logger

    @staticmethod
    def _norm_xy(x: float, y: float, x_lim: tuple[float, float], y_lim: tuple[float, float], normalize: bool) -> tuple[float, float]:
        if not normalize:
            return float(x), float(y)
        x0, x1 = x_lim; y0, y1 = y_lim
        xn = 2.0 * (float(x) - x0) / (x1 - x0) - 1.0
        yn = 2.0 * (float(y) - y0) / (y1 - y0) - 1.0
        return xn, yn
    
    def _features_from_scene(
        self,
        agent_conts: dict[str, FRODOAgentContainer],
        task_conts: dict[str, TaskContainer],
        *,
        normalize: bool,
        x_lim: tuple[float, float],
        y_lim: tuple[float, float],
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Extract feature tensors from agent and task containers.

        Args:
            agent_conts: Dict of agent containers by ID
            task_conts: Dict of task containers by ID
            normalize: Whether to normalize x,y to [-1, 1]
            x_lim: Environment x limits
            y_lim: Environment y limits

        Returns:
            Tuple of (agent_features, task_features) tensors
            - Agent features: [x, y, cos(psi), sin(psi)]
            - Task features: [x, y, cos(psi), sin(psi)]
        """
        A, T = [], []

        # Process agents (sorted by ID for consistent ordering)
        for agent_id in sorted(agent_conts.keys()):
            agent_cont = agent_conts[agent_id]
            ax = agent_cont.x
            ay = agent_cont.y
            ath = agent_cont.psi
            ax, ay = self._norm_xy(ax, ay, x_lim, y_lim, normalize)
            A.append([ax, ay, math.cos(ath), math.sin(ath)])

        # Process tasks (sorted by ID for consistent ordering)
        for task_id in sorted(task_conts.keys()):
            task_cont = task_conts[task_id]
            tx = task_cont.x
            ty = task_cont.y
            tth = task_cont.psi
            tx, ty = self._norm_xy(tx, ty, x_lim, y_lim, normalize)
            T.append([tx, ty, math.cos(tth), math.sin(tth)])

        return torch.tensor(A, dtype=torch.float32), torch.tensor(T, dtype=torch.float32)

    @staticmethod
    def _matches_to_ycols(
        matches: list[tuple[str, str]],
        agent_ids: list[str],
        task_ids: list[str]
    ) -> torch.Tensor:
        """Convert string ID matches to integer index labels.

        Args:
            matches: List of (agent_id, task_id) string tuples
            agent_ids: Sorted list of agent IDs (defines index mapping)
            task_ids: Sorted list of task IDs (defines index mapping)

        Returns:
            Tensor of shape (n_agents,) where y[i] = task index assigned to agent i
            Value is -1 if agent is not assigned
        """
        n = len(agent_ids)
        y = torch.full((n,), -1, dtype=torch.long)

        # Create ID to index mappings
        agent_id_to_idx = {aid: i for i, aid in enumerate(agent_ids)}
        task_id_to_idx = {tid: i for i, tid in enumerate(task_ids)}

        for agent_id, task_id in matches:
            agent_idx = agent_id_to_idx[agent_id]
            task_idx = task_id_to_idx[task_id]
            y[agent_idx] = task_idx

        return y
    
    def _clear_simulation(self):
        """Clear all agents and tasks from simulation for next sample."""
        env_cont = self.sim.environment.environment_container

        # Remove all agents from environment
        for agent_id in list(self.sim.agents.keys()):
            agent = self.sim.agents[agent_id]
            self.sim.environment.removeObject(agent)

        # Remove all tasks from environment
        for task_id in list(self.sim.tasks.keys()):
            task = self.sim.tasks[task_id]
            self.sim.environment.removeObject(task)

        # Clear environment container state dicts
        env_cont.state.agent_conts.clear()
        env_cont.state.task_conts.clear()

        # Clear simulation-level dicts
        self.sim.agents.clear()
        self.sim.tasks.clear()

        # Clear environment's objects dict
        self.sim.environment.objects.clear()

        # Reinitialize collision checker if available
        if hasattr(self.sim.environment, 'setup_collision_checker'):
            self.sim.environment.collision_checker = self.sim.environment.setup_collision_checker()

        # Re-initialize occupancy grids if available
        if hasattr(self.sim.environment, 'initialize_occupancy_grids'):
            self.sim.environment.initialize_occupancy_grids()

        # Unfreeze entity creation
        env_cont.state.entities_creation_frozen = False

    def create_dataset(
        self,
        *,
        specs: list[tuple[int, int]],
        method: type[CentralizedStrategyABC] = HungarianStrategyCent,
        normalize_xy: bool = True,
        seed: int | None = 42,
        out_path: str | None = None,
    ) -> dict:
        """Create a training dataset for GNN task assignment.

        Args:
            specs: List of (n_agents, n_samples) tuples specifying how many samples
                   to generate for each agent/task count
            method: Centralized strategy class to use for generating labels
            normalize_xy: Whether to normalize x,y coordinates to [-1, 1]
            seed: Random seed for reproducibility
            out_path: Optional path to save the dataset

        Returns:
            Dict containing samples and metadata
        """
        self.index = 0

        if seed is not None:
            np.random.seed(seed)
            torch.manual_seed(seed)

        # Get environment limits
        limits = self.sim.environment.environment_container.limits
        x_lim = limits[0]
        y_lim = limits[1]

        samples: list[dict] = []
        total_samples = sum(count for _, count in specs)

        for n, count in specs:
            for _ in range(count):
                if self.index % 10 == 0:
                    self.logger.info(f'Created sample {self.index} of {total_samples}')
                self.index += 1

                # Clear previous scene
                self._clear_simulation()

                # Spawn new agents and tasks
                self.sim.spawn_agents(n=n, log_level='WARNING')
                self.sim.spawn_tasks(n=n)

                # Get containers from environment
                agent_conts = self.sim.environment.environment_container.agent_conts
                task_conts = self.sim.environment.environment_container.task_conts

                # Run assignment strategy
                strategy_instance = method()
                result = strategy_instance.solve(agent_conts, task_conts)

                # Extract features
                XA, XT = self._features_from_scene(
                    agent_conts, task_conts,
                    normalize=normalize_xy, x_lim=x_lim, y_lim=y_lim
                )

                if result.matches is None:
                    raise RuntimeError("Strategy returned no matches; expected list of (agent_id, task_id) pairs.")

                # Convert matches to integer indices
                agent_ids = sorted(agent_conts.keys())
                task_ids = sorted(task_conts.keys())
                y_cols = self._matches_to_ycols(result.matches, agent_ids, task_ids)

                # Convert string matches to index matches for compatibility
                agent_id_to_idx = {aid: i for i, aid in enumerate(agent_ids)}
                task_id_to_idx = {tid: i for i, tid in enumerate(task_ids)}
                matches_indexed = [(agent_id_to_idx[a], task_id_to_idx[t]) for a, t in result.matches]

                samples.append({
                    "XA": XA,
                    "XT": XT,
                    "y_cols": y_cols,
                    "n": XA.shape[0],
                    "matches": matches_indexed,
                })

        dataset = {
            "samples": samples,
            "feature_spec": {
                "agent_features": ["x", "y", "cos_theta", "sin_theta"],
                "task_features": ["x", "y", "cos_theta", "sin_theta"],
                "normalize_xy": normalize_xy,
                "x_lim": x_lim,
                "y_lim": y_lim,
                "seed": seed,
                "version": "v2",
            },
            "specs": specs,
            "method": method.__name__,
        }

        if out_path is not None:
            torch.save(dataset, out_path)
            self.logger.info(f'Dataset saved to {out_path}')

        return dataset
    
    def make_dataloader(
        self,
        dataset_or_path: dict | str,
        *,
        batch_size: int = 1,
        shuffle: bool = True,
    ) -> "TorchDataLoader":
        obj = torch.load(dataset_or_path) if isinstance(dataset_or_path, str) else dataset_or_path

        class _SceneDataset(Dataset):
            def __init__(self, data: dict) -> None:
                self.samples = data["samples"]
                self.feature_spec = data["feature_spec"]
            def __len__(self) -> int:
                return len(self.samples)
            def __getitem__(self, idx: int) -> dict:
                return self.samples[idx]

        ds = _SceneDataset(obj)
        if batch_size == 1:
            collate_fn = None
        else:
            def collate_fn(items: list[dict]) -> dict:
                return {
                    "XA": [it["XA"] for it in items],
                    "XT": [it["XT"] for it in items],
                    "y_cols": [it["y_cols"] for it in items],
                    "n": [it["n"] for it in items],
                    "matches": [it["matches"] for it in items],
                }
        return TorchDataLoader(ds, batch_size=batch_size, shuffle=shuffle, collate_fn=collate_fn)

if __name__ == "__main__":
    # Create simulation (run_mode='fast' for non-real-time dataset generation)
    sim = FRODO_general_Simulation(Ts=0.1, limits=((-3, 3), (-3, 3)), run_mode='fast')
    sim.init()

    # Example: Test spawning and assignment
    sim.spawn_agents(3)
    sim.spawn_tasks(3)

    # Get containers
    agent_conts = sim.environment.environment_container.agent_conts
    task_conts = sim.environment.environment_container.task_conts

    # Test random assignment
    random_strategy = RandomStrategyCent()
    random_result = random_strategy.solve(agent_conts, task_conts)
    print(f"Random matches: {random_result.matches}")

    # Test Hungarian assignment
    hungarian_strategy = HungarianStrategyCent()
    hungarian_result = hungarian_strategy.solve(agent_conts, task_conts)
    print(f"Hungarian matches: {hungarian_result.matches}")

    # Create dataset generator and generate training data
    data_generator = DataSetGenerator(sim)
    data = data_generator.create_dataset(
        specs=[(3, 200), (5, 200)],
        out_path='master_thesis/modules/task_assignment/gnn/training_dataset.pt'
    )
    print(f"Generated {len(data['samples'])} training samples")