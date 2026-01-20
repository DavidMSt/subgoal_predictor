import torch
import math
import numpy as np
import os
from scipy.optimize import linear_sum_assignment
from typing import Optional
from core.utils.logging_utils import Logger


class DatasetGenerator:
    """Lightweight dataset generator for GNN task assignment training.

    Generates random agent/task positions and computes optimal assignments
    using scipy's Hungarian algorithm. No simulation required.
    """

    def __init__(
        self,
        limits: tuple[tuple[float, float], tuple[float, float]] = ((-3, 3), (-3, 3)),
        log_level: str = 'INFO',
    ):
        self.limits = limits
        self.x_lim = limits[0]
        self.y_lim = limits[1]
        self.logger = Logger('DatasetGen', log_level)

    def _random_poses(self, n: int) -> np.ndarray:
        """Generate n random poses [x, y, psi] within limits."""
        x = np.random.uniform(self.x_lim[0], self.x_lim[1], n)
        y = np.random.uniform(self.y_lim[0], self.y_lim[1], n)
        psi = np.random.uniform(-np.pi, np.pi, n)
        return np.stack([x, y, psi], axis=1)

    def _compute_cost_matrix(self, agents: np.ndarray, tasks: np.ndarray) -> np.ndarray:
        """Compute Euclidean distance cost matrix."""
        agent_xy = agents[:, :2]
        task_xy = tasks[:, :2]
        diff = agent_xy[:, None, :] - task_xy[None, :, :]
        return np.linalg.norm(diff, axis=2)

    def _hungarian_assignment(self, cost_matrix: np.ndarray) -> list[tuple[int, int]]:
        """Solve optimal assignment using Hungarian algorithm."""
        row_ind, col_ind = linear_sum_assignment(cost_matrix)
        return list(zip(row_ind.tolist(), col_ind.tolist()))

    def _normalize_xy(self, x: float, y: float) -> tuple[float, float]:
        """Normalize coordinates to [-1, 1]."""
        xn = 2.0 * (x - self.x_lim[0]) / (self.x_lim[1] - self.x_lim[0]) - 1.0
        yn = 2.0 * (y - self.y_lim[0]) / (self.y_lim[1] - self.y_lim[0]) - 1.0
        return xn, yn

    def _poses_to_features(self, poses: np.ndarray, normalize: bool = True) -> torch.Tensor:
        """Convert poses to feature tensor [x, y, cos(psi), sin(psi)]."""
        features = []
        for x, y, psi in poses:
            if normalize:
                x, y = self._normalize_xy(x, y)
            features.append([x, y, math.cos(psi), math.sin(psi)])
        return torch.tensor(features, dtype=torch.float32)

    def generate_sample(self, n: int, normalize: bool = True) -> dict:
        """Generate a single training sample."""
        agent_poses = self._random_poses(n)
        task_poses = self._random_poses(n)

        cost_matrix = self._compute_cost_matrix(agent_poses, task_poses)
        matches = self._hungarian_assignment(cost_matrix)

        XA = self._poses_to_features(agent_poses, normalize)
        XT = self._poses_to_features(task_poses, normalize)

        y_cols = torch.full((n,), -1, dtype=torch.long)
        for agent_idx, task_idx in matches:
            y_cols[agent_idx] = task_idx

        return {
            "XA": XA,
            "XT": XT,
            "y_cols": y_cols,
            "n": n,
            "matches": matches,
        }

    def generate(
        self,
        *,
        team_sizes: Optional[list[int]] = None,
        n_samples: int = 10000,
        normalize_xy: bool = True,
        seed: Optional[int] = 42,
        out_dir: str = 'master_thesis/modules/task_assignment/gnn/datasets',
    ) -> dict[int, str]:
        """Generate datasets organized by team size.

        Args:
            team_sizes: List of team sizes. Default: [5, 10, 15, ..., 50]
            n_samples: Number of samples per team size
            normalize_xy: Whether to normalize coordinates to [-1, 1]
            seed: Random seed for reproducibility
            out_dir: Output directory

        Returns:
            Dict mapping team_size -> output file path
        """
        if team_sizes is None:
            team_sizes = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]

        os.makedirs(out_dir, exist_ok=True)
        output_files = {}

        for n in team_sizes:
            self.logger.info(f'Generating dataset for team size n={n}')

            if seed is not None:
                np.random.seed(seed + n * 1000)
                torch.manual_seed(seed + n * 1000)

            samples = []
            for i in range(n_samples):
                if i % 2000 == 0:
                    self.logger.info(f'  Progress: {i}/{n_samples}')
                samples.append(self.generate_sample(n, normalize=normalize_xy))

            out_path = os.path.join(out_dir, f'dataset_n{n:02d}.pt')
            dataset = {
                "samples": samples,
                "feature_spec": {
                    "agent_features": ["x", "y", "cos_theta", "sin_theta"],
                    "task_features": ["x", "y", "cos_theta", "sin_theta"],
                    "normalize_xy": normalize_xy,
                    "x_lim": self.x_lim,
                    "y_lim": self.y_lim,
                    "seed": seed,
                },
                "team_size": n,
                "n_samples": n_samples,
                "method": "Hungarian",
            }

            torch.save(dataset, out_path)
            self.logger.info(f'Saved {out_path} ({n_samples} samples)')
            output_files[n] = out_path

        return output_files


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Generate GNN task assignment datasets')
    parser.add_argument('--team-sizes', type=int, nargs='+', default=None,
                        help='Team sizes (default: 5,10,15,...,50)')
    parser.add_argument('--n-samples', type=int, default=10000,
                        help='Samples per team size')
    parser.add_argument('--out-dir', type=str,
                        default='master_thesis/modules/task_assignment/gnn/datasets')
    parser.add_argument('--seed', type=int, default=42)

    args = parser.parse_args()

    generator = DatasetGenerator(limits=((-3, 3), (-3, 3)))

    print(f"Generating datasets...")
    print(f"  Team sizes: {args.team_sizes or [5,10,15,20,25,30,35,40,45,50]}")
    print(f"  Samples per size: {args.n_samples}")

    output_files = generator.generate(
        team_sizes=args.team_sizes,
        n_samples=args.n_samples,
        seed=args.seed,
        out_dir=args.out_dir,
    )

    print(f"\nGenerated {len(output_files)} files:")
    for n, path in output_files.items():
        print(f"  n={n}: {path}")
