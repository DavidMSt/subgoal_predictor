
from __future__ import annotations

import time
from typing import Type, Dict, Protocol, Callable, Sequence, Literal
from enum import Enum, StrEnum, auto


import numpy as np
from numpy.typing import NDArray
from scipy.optimize import linear_sum_assignment

from extensions.simulation.src.core.environment import Object
import extensions.simulation.src.core as core
from dataclasses import dataclass

from logging import Logger
import logging

from master_thesis.general.general_simulation import FRODO_general_Simulation, FrodoGeneralEnvironment
from master_thesis.general.general_agents import FRODOGeneralAgent
from master_thesis.task_assignment.task_agent import FRODO_AssignmentAgent
from master_thesis.task_assignment.task_objects import Task

from abc import ABC, abstractmethod
from typing import Any, Tuple

import math
import torch
from torch.utils.data import Dataset, DataLoader as TorchDataLoader

class StrategyABC(ABC):
    default_mode = "central"

    def __init__(self) -> None:
        super().__init__()

    @dataclass
    class AssignmentContext:
        """ 
        Datacontainer that is passed through the individual functions. 
        Enables to be flexible concerning the output assignment result without making the Strategies have a state
        """
        agents: tuple[FRODO_AssignmentAgent, ...]
        tasks: tuple[Task, ...]
        scores: np.ndarray | None = None
        matches: list[tuple[int,int]]| None = None

    class RunningMode(StrEnum):
        """
        Decide in which mode the strategy should be runnning. 
        Especially relevant for things like CTDE (Cetnralized training, decentralized execution) in learning-based strategies

        Args:
            StrEnum (_type_): _description_
        """
        CENTRAL = 'central'
        LOCAL = 'local'


    @abstractmethod
    def central(self, ctx: AssignmentContext, logger: Logger | None = None) -> AssignmentContext:
        """Run centralized solver using sim.env (agents, tasks, costs)."""
        ...

    @abstractmethod
    def local(self, ctx, logger: Logger | None = None) -> Any:
        """Run per-agent step (decentralized)."""
        ...

    def run(self, agents: Tuple[FRODO_AssignmentAgent, ...], tasks: Tuple["Task", ...], logger: Logger | None = None, mode = None) -> Any:
        mode = (mode or getattr(self, "default_mode"))

        ctx = self.AssignmentContext(agents, tasks)

        # Extract agents and tasks
        n_agents = len(ctx.agents)
        n_tasks = len(ctx.tasks)

        # check if one-to one is possible
        if n_agents != n_tasks:
            if logger is not None:
                logger.error('number of tasks and agents must be equal for one-to-one assignments - only case code can handle')
            else:
                raise ValueError('number of tasks and agents must be equal for one-to-one assignments - only case code can handle')

                # Clear existing assignments
        for agent in agents:
            agent.asi._available_tasks.clear()
            agent.asi._assigned_tasks.clear()

        if mode == self.RunningMode.CENTRAL: 
            ctx = self.central(ctx, logger)
        
        elif mode == self.RunningMode.LOCAL:
            ctx = self.local(ctx, logger)

        else:
            if logger is not None:
                logger.error("Mode for assignment strategy is not compatible, choose either local or central")
            else: 
                raise ValueError("Mode for assignment strategy is not compatible, choose either local or central")
            
        result = self.create_assignment_result(ctx=ctx)

        return result

    def create_assignment_result(self, ctx: AssignmentContext) -> AssignmentResult:
        """
        Create an assignment result from the provided context.
        Computes the assignment_matrix from ctx.matches.
        """
        n_agents = len(ctx.agents)
        n_tasks = len(ctx.tasks)
        assignment = np.zeros((n_agents, n_tasks), dtype=np.bool_)
        if ctx.matches is not None:
            for i, j in ctx.matches:
                assignment[i, j] = True
        result = AssignmentResult(
            agent_configurations=[agent.getConfiguration for agent in ctx.agents],
            task_configurations=[task.position for task in ctx.tasks],
            strategy=self,
            assignment_matrix=assignment,
            matches=ctx.matches
        )
        return result

class RandomStrategy(StrategyABC):
    default_mode = "central"

    def central(self, ctx, logger: Logger | None = None) -> StrategyABC.AssignmentContext:
        """Run centralized solver using sim.env (agents, tasks, costs)."""

        # Extract agents and tasks
        n_agents = len(ctx.agents)
        n_tasks = len(ctx.tasks)

        rng = np.random.default_rng()
        assignment = np.zeros((n_agents, n_tasks), dtype=np.bool_)
        m = min(n_agents, n_tasks)
        rows = rng.choice(n_agents, size=m, replace=False)
        cols = rng.choice(n_tasks, size=m, replace=False)  # or np.arange(m) if you prefer
        assignment[rows, cols] = True
        ctx.matches = list(zip(rows.tolist(), cols.tolist()))
        return ctx
    
    def local(self, ctx, logger: Logger | None = None) -> None:
        """Run per-agent step (decentralized)."""
        raise NotImplementedError

# ----------- HungarianStrategy -----------
class HungarianStrategy(StrategyABC):
    default_mode = "central"

    def central(self, ctx: StrategyABC.AssignmentContext, logger: Logger | None = None) -> StrategyABC.AssignmentContext:
        """Centralized Hungarian assignment using per-agent cost vectors."""
        n_agents = len(ctx.agents)
        n_tasks = len(ctx.tasks)
   
        # Build cost matrix from agents' cost vectors (assumes same task ordering)
        cost_matrix = np.zeros((n_agents, n_tasks), dtype=np.float64)
        for i, agent in enumerate(ctx.agents):
            cost_vector_i = agent.asi.compute_task_cost_vector(tasks= ctx.tasks)
            if len(cost_vector_i) != n_tasks:
                msg = (
                    f"Agent {i} provided a cost vector of length {len(cost_vector_i)} "
                    f"but there are {n_tasks} tasks."
                )
                (logger.error(msg) if logger else None)
                raise ValueError(msg)
            cost_matrix[i, :] = cost_vector_i

        row_ind, col_ind = linear_sum_assignment(cost_matrix)
        
        assignment = np.zeros((n_agents, n_tasks), dtype=np.bool_)
        assignment[row_ind, col_ind] = True

        ctx.matches = list(zip(row_ind.tolist(), col_ind.tolist()))
        # Assign selected task to each agent (one-to-one)
        for a_idx, t_idx in ctx.matches:
            ctx.agents[a_idx].asi._assigned_tasks = [ctx.tasks[t_idx]]
        return ctx
    
    def local(self, ctx: StrategyABC.AssignmentContext, logger: Logger | None = None) -> None:
        """Run per-agent step (decentralized)."""
        raise NotImplementedError

class CBBAStrategy(StrategyABC):
    def central(self, ctx:StrategyABC.AssignmentContext, logger: Logger | None = None) -> StrategyABC.AssignmentContext:
        """Run centralized solver using sim.env (agents, tasks, costs)."""
        ...

    def local(self, ctx, logger: Logger | None = None) -> None:
        """Run per-agent step (decentralized)."""
        ...

class GNNStrategy(StrategyABC):
    default_mode = "local"
    def central(self, ctx: StrategyABC.AssignmentContext, logger: Logger | None = None) -> StrategyABC.AssignmentContext:
        """Run centralized solver using sim.env (agents, tasks, costs)."""
        ...

    def local(self, ctx: StrategyABC.AssignmentContext, logger: Logger | None = None) -> None:
        """Run per-agent step (decentralized)."""
        raise NotImplementedError

class TwoTowersStrategy(StrategyABC):
    default_mode = "local"

    def central(self, ctx: StrategyABC.AssignmentContext, logger: Logger | None = None) -> StrategyABC.AssignmentContext:
        ...

    def local(self, ctx: StrategyABC.AssignmentContext, logger: Logger | None = None) -> None:
        """Run per-agent step (decentralized)."""
        ...

@dataclass(frozen=True)
class AssignmentResult:
    agent_configurations: list[core.spaces.State]
    task_configurations: list[core.spaces.State]
    strategy: StrategyABC
    assignment_matrix: NDArray[np.bool_] | None      # shape: (n_agents, n_tasks)
    matches: list[tuple[int, int]] | None             # (agent_idx, task_idx)
    # total_cost: float                           # sum of chosen costs

class AgentFactory(Protocol):
    """Class with callable, provides needed structure (in and output) for agent creation methods used by the sim

    Args:
        Protocol (_type_): _description_
    """
    def __call__(
        self,
        agent_id: str,
        agent_class: Type[FRODO_AssignmentAgent],
        start_config: Sequence[float],
        dt: float
    ) -> FRODO_AssignmentAgent: ...

class AssignmentSimulationModule():

    def __init__(self, env:FrodoGeneralEnvironment, logger: Logger, add_virtual_agent: AgentFactory, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.env = env
        self.logger = logger
        self._add_virual_agent = add_virtual_agent

    @property
    def _agents(self) -> tuple[FRODO_AssignmentAgent, ...]: # TODO: Remove since unnecessary? 
        return tuple([obj for obj in self.env.objects.values() if isinstance(obj, FRODO_AssignmentAgent)])

    @property
    def _tasks(self) -> tuple[Task, ...]:
        return tuple([obj for obj in self.env.objects.values() if isinstance(obj, Task)])

    def spawn_agents(self, n: int, configurations:list[tuple[float, float, float]] | None = None, agent_class: Type[FRODO_AssignmentAgent] = FRODO_AssignmentAgent):
        
        current_number_agents = len(self._agents)
        
        if configurations is not None and n != len(configurations):
            self.logger.error('Spawning agents: If positions is not None, n must equal amount of agents to be spawned')
        
        # get the environments limits for x and y
        pos_dim = self.env.space.dimensions[0]
        x_lim = pos_dim.limits[0]
        y_lim = pos_dim.limits[1]
        
        if configurations is None:
            configurations = []
            # randomly spawn n agents within the environment limits
            for _ in range(n):
                x = np.random.uniform(x_lim[0], x_lim[1])
                y = np.random.uniform(y_lim[0], y_lim[1])
                theta = (np.random.uniform(0.0, 2.0 * np.pi) + np.pi) % (2.0 * np.pi) - np.pi
                configurations.append((x, y, theta))
        
        # spawn the agents
        for i in range(n):
            self._add_virual_agent(f"task_agent_{current_number_agents}", agent_class= agent_class, start_config = configurations[i], dt = self.env.Ts)
            current_number_agents += 1

    def spawn_tasks(self, n: int, configurations: list[tuple[float, float, float]] | None = None):
        """
        Spawn tasks in the environment.
        If positions is None, tasks are spawned uniformly at random inside env limits.
        Tasks only have (x, y), no heading.
        """
        current_number_tasks = len(self._tasks)

        if configurations is not None and n != len(configurations):
            self.logger.error('Spawning tasks: If positions is not None, n must equal amount of tasks to be spawned')

        # get environment limits (assumes rectangular 2D space)
        pos_dim = self.env.space.dimensions[0]
        x_lim = pos_dim.limits[0]
        y_lim = pos_dim.limits[1]

        # generate random positions if none provided
        if configurations is None:
            configurations = []
            for _ in range(n):
                x = np.random.uniform(x_lim[0], x_lim[1])
                y = np.random.uniform(y_lim[0], y_lim[1])
                theta = (np.random.uniform(0.0, 2.0 * np.pi) + np.pi) % (2.0 * np.pi) - np.pi
                configurations.append((x, y, theta))

        # spawn the tasks
        for i in range(n):
            task_id = f"task_{current_number_tasks}"
            new_task = Task(id=task_id, position=configurations[i][:2], orientation= configurations[i][2])
            self.env.addObject(new_task)
            current_number_tasks += 1

    def assign_tasks(
        self,
        method: type[StrategyABC] = HungarianStrategy,
        *,
        mode: StrategyABC.RunningMode | str | None = None,
    ) -> AssignmentResult:
        """Assign tasks to agents using the assignment manager."""
        agents = self._agents
        tasks = self._tasks
        if not agents or not tasks:
            raise ValueError("No agents or tasks available for assignment.")
        
        # push tasks to the agents
        for agent in agents:
            agent.asi.clear_tasks()
            agent.asi.add_tasks(tasks)

        strategy = method()
        return strategy.run(agents, tasks, self.logger, mode=mode)

    def get_agent_positions(self) -> list[tuple[float, float]]:
        """Get the positions of all agents in the environment."""
        agents = self._agents
        return [agent.position for agent in agents]

    def get_task_positions(self) -> list[tuple[float, float]]:
        """Get the positions of all tasks in the environment."""
        tasks = self._tasks
        return [task.position for task in tasks]

    def clear_objects(self):
        """Clear all objects in the environment."""
        self.logger.info('Removing all existing agents and tasks from the environment!')
        for obj in list(self.env.objects.values()):
            self.env.removeObject(obj)



class DataSetGenerator:

    def __init__(self, asi: "AssignmentSimulationModule") -> None:
        self.asi = asi
        self.index = 0
        self.logger = asi.logger

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
        agents: tuple["FRODO_AssignmentAgent", ...],
        tasks: tuple["Task", ...],
        *,
        normalize: bool,
        x_lim: tuple[float, float],
        y_lim: tuple[float, float],
    ) -> tuple[torch.Tensor, torch.Tensor]:
        A, T = [], []
        for ag, tk in zip(agents, tasks):  # assume same length
            # Agent features
            state = ag.configuration
            ax = state[0]['x']
            ay = state[0]['y']
            ath = state[1].value
            ax, ay = self._norm_xy(ax, ay, x_lim, y_lim, normalize)
            A.append([ax, ay, math.cos(ath), math.sin(ath)])

            # Task features
            tx, ty = tk.position
            tx, ty = self._norm_xy(tx, ty, x_lim, y_lim, normalize)
            tth = tk.configuration[1].value
            T.append([tx, ty, math.cos(tth), math.sin(tth)])

        return torch.tensor(A, dtype=torch.float32), torch.tensor(T, dtype=torch.float32)

    @staticmethod
    def _matches_to_ycols(matches: list[tuple[int, int]], n: int) -> torch.Tensor:
        y = torch.full((n,), -1, dtype=torch.long)
        for i, j in matches:
            y[int(i)] = int(j)
        return y
    
    def create_dataset(
        self,
        *,
        specs: list[tuple[int, int]],
        method: type["StrategyABC"] = HungarianStrategy,
        normalize_xy: bool = True,
        seed: int | None = 42,
        out_path: str | None = None,
    ) -> dict:
        self.index = 0

        if seed is not None:
            np.random.seed(seed)
            torch.manual_seed(seed)

        pos_dim = self.asi.env.space.dimensions[0]
        x_lim = (pos_dim.limits[0][0], pos_dim.limits[0][1])
        y_lim = (pos_dim.limits[1][0], pos_dim.limits[1][1])

        samples: list[dict] = []
        total_samples = sum(count for _, count in specs)
        for n, count in specs:
            for _ in range(count):
                if self.index % 10 == 0:
                    self.logger.info(f'created sample {self.index} of {total_samples}')
                self.index += 1
                self.asi.clear_objects()
                self.asi.spawn_agents(n=n, configurations=None)
                self.asi.spawn_tasks(n=n, configurations=None)

                result = self.asi.assign_tasks(method=method)
                agents = self.asi._agents
                tasks = self.asi._tasks

                XA, XT = self._features_from_scene(agents, tasks, normalize=normalize_xy, x_lim=x_lim, y_lim=y_lim)
                if result.matches is None:
                    raise RuntimeError("AssignmentResult.matches is None; expected list of (agent, task) pairs.")
                y_cols = self._matches_to_ycols(result.matches, n=len(agents))

                samples.append({
                    "XA": XA,
                    "XT": XT,
                    "y_cols": y_cols,
                    "n": XA.shape[0],
                    "matches": result.matches,
                })

        dataset = {
            "samples": samples,
            "feature_spec": {
                "agent_features": ["x", "y", "cos_theta", "sin_theta"],
                "task_features": ["x", "y"],
                "normalize_xy": normalize_xy,
                "x_lim": x_lim,
                "y_lim": y_lim,
                "seed": seed,
                "version": "v1",
            },
            "specs": specs,
            "method": method.__name__,
        }
        if out_path is not None:
            torch.save(dataset, out_path)
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


class FRODO_AssignmentSimulation(FRODO_general_Simulation):
    def __init__(self, Ts=0.1, use_web_interface: bool = False, min_values: list[int] = [-3,3], max_values: list[int] = [3,3], env=FrodoGeneralEnvironment):
        super().__init__(Ts, use_web_interface, min_values, max_values, env)

        self.asi = AssignmentSimulationModule(self.env, self.logger, self.addVirtualAgent)


def assignment_example():
    # create simulation (no web gui)
    sim = FRODO_AssignmentSimulation(Ts=0.1, use_web_interface=False, min_values= [-3, -3], max_values=[3,3])
    
    # spawn agents
    sim.asi.spawn_agents(3)
    sim.asi.spawn_agents(n = 2, configurations = [(0.1,2.2,np.pi),(0.2,0.3,0.0)])

    # spawn tasks
    sim.asi.spawn_tasks(3)
    sim.asi.spawn_tasks(n = 2)
    
    # do assignments
    random_result = sim.asi.assign_tasks(method=RandomStrategy)
    # print(random_result.assignment_matrix)

    hungarian_result = sim.asi.assign_tasks(method= HungarianStrategy)
    # print(hungarian_result.assignment_matrix)

    data_generator = DataSetGenerator(sim.asi)
    data = data_generator.create_dataset(specs = [(3,200), (5,200)], out_path = 'applications/master_david/task_assignment/helper/training_dataset.pt')


    while True:
        time.sleep(1)

# --------- Example Usage ---------
if __name__ == "__main__":

    assignment_example()
