import dataclasses


@dataclasses.dataclass
class SimulatedBILBO_State:
    x: float
    z: float
    v: float
    theta: float
    theta_dot: float


@dataclasses.dataclass
class SimulatedBILBO_Config:
    wheel_diameter: float
    height: float
    width: float


# === SIMULATED BILBO ==================================================================================================
class SimulatedBILBO:
    state: SimulatedBILBO_State
    config: SimulatedBILBO_Config

    # === INIT =========================================================================================================
    def __init__(self):
        ...

    # === METHODS ======================================================================================================


@dataclasses.dataclass
class EnvironmentObject:
    id: str
    width: int  # in tiles
    height: int  # in tiles
    row: int  # Vertical position in the grid
    column: int  # Horizontal position in the grid


# === OBSTACLE =========================================================================================================
@dataclasses.dataclass
class Obstacle_Config:
    explosive: bool = False


class Obstacle(EnvironmentObject):
    config: Obstacle_Config


# === PLATFORM =========================================================================================================
@dataclasses.dataclass
class Platform_Config:
    friction: float = 1.0
    bounce: float = 1.0


class Platform(EnvironmentObject):
    config: Platform_Config


# === RAMP =============================================================================================================
@dataclasses.dataclass
class Collectible_Config:
    points: int


@dataclasses.dataclass
class Collectible(EnvironmentObject):
    config: Collectible_Config
    collected: bool = False


# === ENVIRONMENT ======================================================================================================
@dataclasses.dataclass
class Environment_Config:
    width: int  # in tiles
    height: int  # in tiles


class Environment:
    robot: SimulatedBILBO
    object: dict[str, EnvironmentObject]

    # === INIT =========================================================================================================
    def __init__(self):
        ...

    def step(self):
        # 1. Simulate the robot

        # 2. Simulate the interaction between the robot and the environment objects
        ...


# === SIMULATION =======================================================================================================
class BILBO_Game_Simulation:
    robot: SimulatedBILBO

    # === INIT =========================================================================================================
    def __init__(self):
        ...

    # === METHODS ======================================================================================================
