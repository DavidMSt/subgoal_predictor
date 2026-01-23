
from extensions.simulation.src import core as core


class BaseEnvironment(core.environment.Environment):
    """
    A simple dynamic simulation world.
    It schedules various phases during each simulation cycle:
      - Input
      - Sensors
      - Communication
      - Logic
      - Dynamics
      - Physics Update
      - Collision
      - Additional Logic
      - Output
    """
    space = core.spaces.Space3D()

    def __init__(self, Ts, run_mode, *args, **kwargs):
        super().__init__(Ts, run_mode, space=self.space, *args, **kwargs)
