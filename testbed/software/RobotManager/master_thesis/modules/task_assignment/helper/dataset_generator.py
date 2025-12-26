import torch
import math
import numpy as np
from testbed.software.RobotManager.master_thesis.task_assignment.ta_simulation import AssignmentSimulationModule, FRODO_AssignmentSimulation
from master_thesis.task_assignment.strategies.centralized_strategies import RandomStrategyCent, HungarianStrategyCent, BaseStrategy
from testbed.software.RobotManager.master_thesis.task_assignment.ta_agent import FRODO_AssignmentAgent
from master_thesis.general.general_task import GeneralTask
from torch.utils.data import Dataset, DataLoader as TorchDataLoader

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
        tasks: tuple["GeneralTask", ...],
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
        method: type["BaseStrategy"] = HungarianStrategyCent,
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
                    raise RuntimeError("AssignmentContextContainer matches is None; expected list of (agent, task) pairs.")
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

if __name__ == "__main__": 
        # create simulation (no web gui)
    sim = FRODO_AssignmentSimulation(Ts=0.1, limits=((-3,3), (3,3)))
    
    # spawn agents
    sim.asi.spawn_agents(3)
    sim.asi.spawn_agents(n = 2, configurations = [(0.1,2.2,np.pi),(0.2,0.3,0.0)])

    # spawn tasks
    sim.asi.spawn_tasks(3)
    sim.asi.spawn_tasks(n = 2)
    
    # do assignments
    random_result = sim.asi.assign_tasks(method=RandomStrategyCent)
    # print(random_result.assignment_matrix)

    hungarian_result = sim.asi.assign_tasks(method= HungarianStrategyCent)
    # print(hungarian_result.assignment_matrix)

    data_generator = DataSetGenerator(sim.asi)
    data = data_generator.create_dataset(specs = [(3,200), (5,200)], out_path = 'applications/master_david/task_assignment/helper/training_dataset.pt')