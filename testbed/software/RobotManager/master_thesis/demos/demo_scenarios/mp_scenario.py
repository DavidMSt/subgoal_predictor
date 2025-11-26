import numpy as np

from master_thesis.universal.universal_simulation import FRODO_universal_Simulation
from master_thesis.universal.universal_agent import FRODOUniversalAgent
from master_thesis.demos.thesis_demo import ThesisDemo

class ScenarioBase:
    def __init__(self, demo: ThesisDemo):
        self.demo = demo

    def setup(self):
        """Called once when user selects scenario."""
        raise NotImplementedError

    def reset(self):
        """Optional – undo changes or reset world."""
        pass

class DemoCorridor(ScenarioBase):

    def setup(self):
        r = self.demo.addRobot("frodo")

        # build a corridor
        self.demo.addObstacle("wall_left", x=0.0, y=1.0, length=5)
        self.demo.addObstacle("wall_right", x=0.0, y=-1.0, length=5)

        # position robot
        r.sim_agent.set_position(x=-2.0, y=0.0, psi=0.0)

        # give it a goal
        self.demo.sim.assign_goal("frodo", x=2.0, y=0.0)