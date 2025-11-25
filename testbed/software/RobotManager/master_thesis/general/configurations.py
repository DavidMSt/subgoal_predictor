from dataclasses import dataclass
import numpy as np

@dataclass(frozen= False, slots= False) # must be dynamically changeable since env can change
class EnvironmentConfig:
    limits: list[list[float]]
    obstacles: list[dict]
    Ts: float

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