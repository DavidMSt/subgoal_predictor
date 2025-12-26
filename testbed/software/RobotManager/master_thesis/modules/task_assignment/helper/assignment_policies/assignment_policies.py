from typing import Protocol, Dict
from abc import ABC, abstractmethod
from enum import Enum, auto
import numpy as np
from numpy.typing import NDArray
from scipy.optimize import linear_sum_assignment

class PolicySelection(Enum):
    HUNGARIAN = auto()  
    RANDOM = auto()    # TODO 
    CBBA = auto()      # TODO
    GNN = auto()   

class AssignmentPolicy(ABC):
    @abstractmethod
    def assign(
        self,
        *,
        agent_positions: NDArray[np.float32],   # [N,2]
        task_positions: NDArray[np.float32],    # [M,2]
    ) -> NDArray[np.bool_]:  # [N,M] one-hot rows (or may contain conflicts initially)
        ...

class HungarianPolicy(AssignmentPolicy):
    def __init__(self, cost_fn=None):
        self.cost_fn = cost_fn or (lambda A,T: np.linalg.norm(A[:,None,:]-T[None,:,:], axis=-1))

    def assign(self, *, agent_positions: NDArray[np.float32], task_positions: NDArray[np.float32]) -> NDArray[np.bool_]:
        C = self.cost_fn(agent_positions.astype(np.float64), task_positions.astype(np.float64))
        rows, cols = linear_sum_assignment(C)
        A = np.zeros_like(C, dtype=bool); A[rows, cols] = True
        return A


class GNNPolicy(AssignmentPolicy):
    def __init__(self, predict_fn, M_max: int = 64):
        self.predict = predict_fn
        self.M_max = int(M_max)

    def _obs(self, agent_xy: np.ndarray, task_xy: np.ndarray) -> dict[str, np.ndarray]:
        dxy = task_xy - agent_xy[None,:]
        dist = np.linalg.norm(dxy, axis=1, keepdims=True)
        feats = np.concatenate([dxy, dist], axis=1).astype(np.float32)
        M = feats.shape[0]
        if M > self.M_max:
            feats = feats[:self.M_max]; mask = np.ones((self.M_max,), np.int8)
        else:
            pad = self.M_max - M
            mask = np.zeros((self.M_max,), np.int8); mask[:M] = 1
            if pad: feats = np.vstack([feats, np.zeros((pad,3), np.float32)])
        return {"agent": agent_xy.astype(np.float32), "tasks": feats, "task_mask": mask}

    def assign(self, *, agent_positions: NDArray[np.float32], task_positions: NDArray[np.float32]) -> NDArray[np.bool_]:
        N, M = agent_positions.shape[0], task_positions.shape[0]
        A = np.zeros((N,M), dtype=bool)
        for i in range(N):
            j = int(self.predict(self._obs(agent_positions[i], task_positions)))
            if 0 <= j < min(M, self.M_max): A[i,j] = True
        return A