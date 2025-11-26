import numpy as np

from universal.universal_simulation import FRODO_universal_Simulation
from universal.universal_agent import FRODOUniversalAgent

class ScenarioBase:
    def __init__(self, demo: ThesisDemo):
        self.demo = demo

    def setup(self):
        """Called once when user selects scenario."""
        raise NotImplementedError

    def reset(self):
        """Optional – undo changes or reset world."""
        pass
