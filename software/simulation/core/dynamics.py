import dataclasses
from abc import ABC, abstractmethod
from typing import Union, Any

import control
import numpy as np

from . import spaces as sp
from .environment import Object
from ..core.scheduling import ScheduledObject, Action


@dataclasses.dataclass
class DynamicsSpaces:
    state_space: sp.Space = None
    input_space: sp.Space = None
    output_space: sp.Space = None


class Dynamics(ScheduledObject):
    state_space: sp.Space
    input_space: sp.Space
    output_space: sp.Space
    state: sp.State
    input: sp.State
    output: sp.State
    Ts: float
    state_initial: sp.State

    # === INIT =========================================================================================================
    def __init__(self, Ts: float = None, state: Union[sp.State, list] = None, *args,
                 **kwargs):
        super().__init__(*args, **kwargs)

        update_action = Action(function=self.update, lambdas={'input': lambda: self.input})

        self.addAction(update_action)

        if isinstance(self.input_space, type):
            self.input_space = self.input_space()

        if isinstance(self.output_space, type):
            self.output_space = self.output_space()

        if isinstance(self.state_space, type):
            self.state_space = self.state_space()


        if state is None:
            state = self.state_space.getState()

        self.state = state
        self.input = self.input_space.getState()

        if Ts is not None:
            self.Ts = Ts  # TODO: or should this be taken from somewhere else?

    # === PROPERTIES ===================================================================================================
    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        self._state = self.state_space.map(value)

    @property
    def input(self):
        return self._input

    @input.setter
    def input(self, value):
        self._input = self.input_space.map(value)

    @property
    def output(self):
        return self._output(self.state)

    @output.setter
    def output(self, value):
        raise Exception("Cannot set the output directly")

    # === METHODS ======================================================================================================
    def update(self, input=None):
        if input is not None:
            self.input = input

        self.state = self._dynamics(self.state, self.input)
        print(f"Input: {self.input}, State: {self.state}")
        pass

    # ------------------------------------------------------------------------------------------------------------------
    def reset(self):
        pass

    # === PRIVATE METHODS ==============================================================================================
    @abstractmethod
    def _dynamics(self, state: sp.State, input: sp.State):
        pass

    @abstractmethod
    def _output(self, state: sp.State):
        pass


# ======================================================================================================================
class LinearDynamics(Dynamics):
    A: np.ndarray
    B: np.ndarray
    C: np.ndarray
    D: np.ndarray

    sys: control.StateSpace
    sys_cont: control.StateSpace

    n: int
    p: int
    q: int

    def __init__(self, Ts: float = None, state: Union[sp.State, list] = None,
                 discrete: bool = False, *args,
                 **kwargs):
        super().__init__(Ts, state, *args, **kwargs)

        self.A = np.asarray(self.A)
        self.B = np.asarray(self.B)
        self.C = np.asarray(self.C)
        self.D = np.asarray(self.D)

        self.n = np.shape(self.A)[0]
        self.p = np.shape(self.B)[1]
        self.q = np.shape(self.C)[0]

        if not hasattr(self, 'discrete'):
            self.discrete = discrete

        self.sys = control.StateSpace(self.A, self.B, self.C, self.D, self.Ts, remove_useless_states=False)

    def _output(self, state: sp.State):
        pass

    def _dynamics(self, state: sp.State, input: sp.State):
        x = self.A @ state + self.B @ input
        return x

    def init(self):
        pass


# ======================================================================================================================
class DynamicObject(Object, ABC):
    dynamics: Dynamics

    input: Any

    # === INIT =========================================================================================================
    def __init__(self, object_id, space: sp.Space = None, *args, **kwargs):
        super().__init__(object_id=object_id, space=space, *args, **kwargs)

        self.input = None
        self.output = None

        # Register the dynamics action in the World Dynamics Phase

    # === PROPERTIES ===================================================================================================

    def simulate(self, input: list | np.ndarray = None,
                 steps=None,
                 zero_initial_step: bool = True,
                 x0: list | np.ndarray = None,
                 reset: bool = True):

        if steps is None and input is not None:
            steps = len(input)

        if steps is None:
            raise Exception("No simulation steps specified. Please specify either input or steps.")

        if input is not None:
            if steps > len(input):
                raise Exception("The number of simulation steps is larger than the number of inputs.")

        if x0 is not None:
            self.state = x0
        elif reset:
            if hasattr(self, 'reset'):
                self.reset()
            elif hasattr(self.dynamics, 'reset'):
                self.dynamics.reset()

        if zero_initial_step:
            output = [None] * (steps + 1)

            self.scheduling.actions['step']()
            output[0] = self.output
        else:
            output = [None] * steps

        self.scheduling.actions['init']()
        self.scheduling.actions['start']()

        for i in range(steps):
            if input is not None:
                self.input = input[i]

            self.scheduling.actions['entry']()
            self.scheduling.actions['step']()

            self.scheduling.actions['exit']()

            output[i + 1] = self.output

        self.scheduling.actions['stop']()

        return output

    @property
    def state(self):
        return self.dynamics.state

    @state.setter
    def state(self, value):
        self.dynamics.state.set(value)

    @property
    def configuration(self):
        return self.space.map(self.dynamics.state)

    @configuration.setter
    def configuration(self, value):
        raise Exception("Cannot set configuration of dynamic world object. Set the state instead.")

    def setConfiguration(self, value, dimension=None, subdimension=None, space='local'):
        assert (space == 'local' or space == 'global' or space == self.space or space == self.space_global)

        config_temp = self.space.map(self._configuration)
        if dimension is None:
            config_temp = self.space.map(value)
        else:
            if subdimension is None:
                config_temp[dimension] = value
            else:
                config_temp[dimension][subdimension] = value

        self._configuration = config_temp
        self.state = self.dynamics.state_space.map(config_temp)
        self._updatePhysics(self.configuration)

    # === METHODS ======================================================================================================

    # === ACTIONS ======================================================================================================
    def action_dynamics(self, *args, **kwargs):
        self.dynamics.update()

    # === PRIVATE METHODS ==============================================================================================
