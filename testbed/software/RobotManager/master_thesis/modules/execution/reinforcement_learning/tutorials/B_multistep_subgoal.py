import gymnasium as gym 
from master_thesis.universal.universal_simulation import FRODO_Universal_Simulation

import numpy as np
from typing import Any
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Range2D:
    min: np.ndarray
    max: np.ndarray

    def __post_init__(self):
        object.__setattr__(self, "min", np.asarray(self.min, dtype=np.float32))
        object.__setattr__(self, "max", np.asarray(self.max, dtype=np.float32))
        
@dataclass(frozen=True, slots = True)
class Range4D:
    range2d_1: Range2D
    range2d_2: Range2D
    # get min max values in the post init function
    min: np.ndarray = field(init=False)
    max: np.ndarray = field(init=False)

    def __post_init__(self):
        # bypass frozen attribute
        object.__setattr__(self, "min", np.concatenate([self.range2d_1.min, self.range2d_2.min], dtype = np.float32))
        object.__setattr__(self, "max", np.concatenate([self.range2d_1.max, self.range2d_2.max], dtype = np.float32))

class FrodoGymWrapper(gym.Env): 
    def __init__(self, sim: FRODO_Universal_Simulation, max_steps: int = 200) -> None:
        ...

    def reset(self, *, seed=None, options=None):
        ...

    def step(self, action):
        ...

    def _get_obs(self):
        ...

    def _compute_reward(self, obs, action):
        ...

    def _check_termination(self, obs):
        ...

    def render(self):
        ...

    def close(self):
        ...
