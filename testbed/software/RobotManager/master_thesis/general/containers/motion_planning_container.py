from dataclasses import dataclass
import numpy as np
from core.utils.states import State # TODO: do I even need this statee import here?

@dataclass(frozen = False, slots=True)
class MotionPlanningState:
    success: bool = False
    message: str | None = None

    # raw planner output
    raw_states: list[np.ndarray] | None = None
    raw_inputs: list[np.ndarray] | None = None
    raw_durations: list[float] | None = None
    raw_delta_t: float | None = None

    # optional post-processing
    smoothed_states: list[np.ndarray] | None = None
    smoothed_inputs: list[np.ndarray] | None = None
    smoothed_delta_t: float | None = None

    # timing / metrics
    computation_time: float | None = None
    path_length: float | None = None
    cost: float | None = None

@dataclass(frozen = True, slots = True)
class MotionPlanningConfig:
    
    # start/ goal configurations
    start: np.ndarray
    goal: np.ndarray | None

    # hyperparameters
    # timelimit for each motion planning problem
    timelimit: float = 60.0
    # bias for goal sampling
    goal_bias: float = 0.1
    # size of the goal region
    goal_eps: float = 0.1
    # weight of so2 relative to r2 in distance metric
    so_r2_weight: float = 0.1
    # select which planner to use
    planner: str = 'rrt'

    # control bounds (only relevant for kinodynamic case)
    theta_dot_bounds: tuple = (-np.pi/3, np.pi/3)
    v_bounds: tuple = (-1.0, 1.0)

@dataclass(slots = True)
class MotionPlannigContainer:
    state: MotionPlanningState
    config: MotionPlanningConfig