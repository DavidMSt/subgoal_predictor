from scipy.optimize import linear_sum_assignment
import numpy as np
from extensions.simulation.src.core.environment import Object
import extensions.simulation.src.core as core
from extensions.simulation.src.core.spaces import Space, State 
from typing import Tuple, cast
import logging
from abc import ABC, abstractmethod
# from master_thesis.task_assignment.assingment_interface import AssignmentAgentInterface

# ----------------------------- Task Classes -----------------------------

class Task(Object):
    def __init__(
        self,
        id,
        position: tuple[float, float] = (0.0, 0.0),
        orientation: float = 0,
        *,
        is_assignable: bool = True,
    ):
        self.space = core.spaces.Space2D()  # quick fix TODO: make clean once Object handles this correctly 
        super().__init__(object_id=id, space=self.space)

        self.assigned = False
        self.is_assignable = is_assignable
        self.setPosition(x = position[0], y = position[1])
        self.setOrientation(orientation)

    def setPosition(self, x=None, y=None, *args, **kwargs):
        if isinstance(x, list):
            x, y = x[0], x[1]
        super().setPosition([x,y])

    @property
    def position(self):
        return [self.configuration_global['pos']['x'], self.configuration_global['pos']['y'] ]

    @property
    def orientation(self):
        return self.configuration['psi'].value

    def setOrientation(self, psi):
        super().setConfiguration(dimension='psi', value=psi)

if __name__ == "__main__":
    t = Task(id = 'task_test')
    t.setPosition(10.3, 2.3)
    t.setOrientation(np.pi)

    t2 = Task(id= 'task_test2', position= (1.3, -1.3), orientation=3*np.pi) # wrapping leads to orientation being 1*np.pi
    
    print(t.configuration)
    print(t2.configuration)
