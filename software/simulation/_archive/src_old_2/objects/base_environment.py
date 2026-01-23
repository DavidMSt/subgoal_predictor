import copy
import dataclasses
import math
import pickle
import random
import time

import control
import matplotlib.pyplot as plt
import numpy as np
from numpy import nan

from extensions.simulation.src import core as core
from extensions.simulation.src.core import spaces as sp
from extensions.simulation.src.utils import lib_control
from extensions.simulation.src.utils.orientations import twiprToRotMat, twiprFromRotMat
from extensions.simulation.src.utils.babylon import setBabylonSettings


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
    Ts = 0.02

    def __init__(self, Ts, run_mode, *args, **kwargs):
        super().__init__(Ts, run_mode, space=self.space, *args, **kwargs)

        core.scheduling.Action(action_id='input', object=self, priority=0, parent=self.action_step,
                               function=self.action_input)
        action_objects = core.scheduling.Action(action_id='objects', object=self, function=self.action_objects,
                                                priority=2,
                                                parent=self.action_step)
        core.scheduling.Action(action_id='visualization', object=self, priority=3, parent=self.action_step,
                               function=self.action_visualization)
        core.scheduling.Action(action_id='output', object=self, priority=4, parent=self.action_step,
                               function=self.action_output)

        # Schedule simulation phases using unique IDs (not "name")
        # core.scheduling.Action(action_id='input', object=self, function=self.action_input, priority=10,
        #                        parent=action_objects)
        core.scheduling.Action(action_id='sensors', object=self, function=self.action_sensors, priority=11,
                               parent=action_objects)
        core.scheduling.Action(action_id='communication', object=self, function=self.action_communication, priority=12,
                               parent=action_objects)
        core.scheduling.Action(action_id='logic', object=self, function=self.action_logic, priority=13,
                               parent=action_objects)
        core.scheduling.Action(action_id='dynamics', object=self, function=self.action_dynamics, priority=14,
                               parent=action_objects)
        core.scheduling.Action(action_id='physics_update', object=self, function=self.action_physics_update,
                               priority=15, parent=action_objects)
        core.scheduling.Action(action_id='collision', object=self, function=self.collisionCheck, priority=16,
                               parent=action_objects)
        core.scheduling.Action(action_id='logic2', object=self, function=self.action_logic2, priority=17,
                               parent=action_objects)
        # core.scheduling.Action(action_id='output', object=self, function=self.action_output, priority=18,
        #                        parent=action_objects)

    # --- Simulation phase actions ---
    def action_input(self, *args, **kwargs):
        """Process external inputs."""
        pass

    def action_sensors(self, *args, **kwargs):
        """Process sensor data."""
        pass

    def action_communication(self, *args, **kwargs):
        """Handle communications among simulation objects."""
        pass

    def action_logic(self, *args, **kwargs):
        """Perform logical decision-making."""
        pass

    def action_dynamics(self, *args, **kwargs):
        """Update dynamics of simulation objects."""
        pass

    def action_environment(self, *args, **kwargs):
        """Update environmental effects if applicable."""
        pass

    def action_logic2(self, *args, **kwargs):
        """Additional logic processing."""
        pass

    def action_output(self, *args, **kwargs):
        """Output simulation results (e.g., visualization)."""
        pass

    def action_physics_update(self, *args, **kwargs):
        """Update the physics of all simulation objects."""
        pass

    def _init(self):
        super()._init()

    def action_controller(self, *args, **kwargs):
        pass

    def action_visualization(self, *args, **kwargs):
        ...

    def action_objects(self, *args, **kwargs):
        pass
