import copy
import dataclasses
import math
import pickle

import control
import matplotlib.pyplot as plt
import numpy as np

from extensions.simulation.src import core as core
from extensions.simulation.src.core import spaces as sp
from extensions.simulation.src.utils import lib_control
from extensions.simulation.src.utils.orientations import twiprToRotMat, twiprFromRotMat
from extensions.simulation.src.utils.babylon import setBabylonSettings

DEFAULT_SAMPLE_TIME = 0.02


@dataclasses.dataclass
class BilboModel:
    """
    Dataclass for the two-wheeled (BILBO) robot model parameters.
    """
    m_b: float
    m_w: float
    l: float
    d_w: float
    I_w: float
    I_w2: float
    I_y: float
    I_x: float
    I_z: float
    c_alpha: float
    r_w: float
    tau_theta: float
    tau_x: float
    max_pitch: float


# Default model parameters (formerly TWIPR_Michael_Model)
DEFAULT_BILBO_MODEL = BilboModel(
    m_b=2.5,
    m_w=0.636,
    l=0.026,
    d_w=0.28,
    I_w=5.1762e-4,
    I_w2=6.1348e-04,
    I_y=0.01648,
    I_x=0.02,
    I_z=0.03,
    c_alpha=4.6302e-4,
    r_w=0.055,
    tau_theta=1,
    tau_x=1,
    max_pitch=np.deg2rad(105)
)


class Space3D_BILBO(core.spaces.Space):
    """
    3D space for BILBO.
    Consists of a 2D position vector and two scalar angles.
    """
    dimensions = [
        core.spaces.VectorDimension(name='pos', base_type=core.spaces.PositionVector2D),
        core.spaces.ScalarDimension(name='theta', limits=[-math.pi, math.pi], wrapping=True),
        core.spaces.ScalarDimension(name='psi', limits=[0, 2 * math.pi], wrapping=True)
    ]

    def _add(self, state1, state2, new_state):
        raise Exception("Addition not allowed in Space3D_BILBO")


class Mapping_BILBO_2_3D(core.spaces.SpaceMapping):
    """
    Mapping from Space3D_BILBO to the standard 3D space.
    """
    space_to = core.spaces.Space3D
    space_from = Space3D_BILBO

    def _map(self, state):
        out = {
            'pos': [state['pos']['x'], state['pos']['y'], 0],
            'ori': twiprToRotMat(state['theta'].value, state['psi'].value)
        }
        return out


class Mapping_3D_2_BILBO(core.spaces.SpaceMapping):
    """
    Mapping from the standard 3D space to Space3D_BILBO.
    """
    space_from = core.spaces.Space3D
    space_to = Space3D_BILBO

    def _map(self, state):
        angles = twiprFromRotMat(state['ori'].value)
        out = {
            'pos': [state['pos']['x'], state['pos']['y']],
            'theta': angles[1],
            'psi': angles[0]
        }
        return out


# Register mappings
Space3D_BILBO.mappings = [Mapping_3D_2_BILBO(), Mapping_BILBO_2_3D()]
core.spaces.Space3D.mappings.append(Mapping_3D_2_BILBO())


class BILBO_PhysicalObject(core.physics.PhysicalBody):
    """
    Physical representation for BILBO.
    """

    def __init__(self, height: float = 0.174, width: float = 0.126, depth: float = 0.064,
                 wheel_diameter: float = 0.13, l_w: float = 0.056, *args, **kwargs):
        super().__init__()
        self.height = height
        self.width = width
        self.depth = depth
        self.wheel_diameter = wheel_diameter
        self.l_w = l_w
        self.bounding_objects = {
            'body': core.physics.CuboidPrimitive(
                size=[self.depth, self.width, self.height],
                position=[0, 0, 0],
                orientation=np.eye(3)
            )
        }
        self.proximity_sphere.radius = self._getProximitySphereRadius()

    def update(self, config, *args, **kwargs):
        v_t = [config['pos']['x'], config['pos']['y'], self.wheel_diameter / 2]
        v_m = [0, 0, self.height / 2 - self.l_w]
        # Multiply vector v_m by orientation (assumed to be a matrix)
        v_m_e = config['ori'] * v_m
        new_position = v_t + v_m_e
        self.bounding_objects['body'].update(new_position, config['ori'].value)
        self._calcProximitySphere()

    def _calcProximitySphere(self):
        self.proximity_sphere.radius = self._getProximitySphereRadius()
        self.proximity_sphere.update(position=self.bounding_objects['body'].position)

    def _getProximitySphereRadius(self):
        return (self.height / 2) * 1.1


# Define several state and input spaces for BILBO.
class BILBO_2D_InputSpace(core.spaces.Space):
    dimensions = [core.spaces.ScalarDimension(name='M')]


class BILBO_2D_StateSpace_4D(core.spaces.Space):
    dimensions = [
        core.spaces.ScalarDimension(name='s'),
        core.spaces.ScalarDimension(name='v'),
        core.spaces.ScalarDimension(name='theta'),
        core.spaces.ScalarDimension(name='theta_dot')
    ]


class BILBO_2D_StateSpace_5D(core.spaces.Space):
    dimensions = [
        core.spaces.ScalarDimension(name='x'),
        core.spaces.ScalarDimension(name='y'),
        core.spaces.ScalarDimension(name='v'),
        core.spaces.ScalarDimension(name='theta'),
        core.spaces.ScalarDimension(name='theta_dot')
    ]


class BILBO_3D_InputSpace(core.spaces.Space):
    dimensions = [
        core.spaces.ScalarDimension(name='M_L'),
        core.spaces.ScalarDimension(name='M_R')
    ]


class BILBO_3D_ExternalInputSpace(core.spaces.Space):
    dimensions = [
        core.spaces.ScalarDimension(name='v'),
        core.spaces.ScalarDimension(name='psi_dot')
    ]


class BILBO_3D_StateSpace_6D(core.spaces.Space):
    dimensions = [
        core.spaces.ScalarDimension(name='s'),
        core.spaces.ScalarDimension(name='v'),
        core.spaces.ScalarDimension(name='theta'),
        core.spaces.ScalarDimension(name='theta_dot'),
        core.spaces.ScalarDimension(name='psi'),
        core.spaces.ScalarDimension(name='psi_dot')
    ]


class BILBO_3D_StateSpace_7D(core.spaces.Space):
    dimensions = [
        core.spaces.ScalarDimension(name='x'),
        core.spaces.ScalarDimension(name='y'),
        core.spaces.ScalarDimension(name='v'),
        core.spaces.ScalarDimension(name='theta', wrapping=False),
        core.spaces.ScalarDimension(name='theta_dot'),
        core.spaces.ScalarDimension(name='psi'),
        core.spaces.ScalarDimension(name='psi_dot')
    ]


class Mapping_BILBO_SS_2_CF(core.spaces.SpaceMapping):
    """
    Mapping from BILBO state space (7D) to configuration space (Space3D_BILBO).
    """
    space_from = BILBO_3D_StateSpace_7D
    space_to = Space3D_BILBO

    def _map(self, state):
        out = {
            'pos': [state['x'], state['y']],
            'theta': state['theta'],
            'psi': state['psi']
        }
        return out


class Mapping_CF_2_BILBO_SS(core.spaces.SpaceMapping):
    """
    Mapping from configuration space (Space3D_BILBO) to BILBO state space (7D).
    """
    space_from = Space3D_BILBO
    space_to = BILBO_3D_StateSpace_7D

    def _map(self, state):
        out = {
            'x': state['pos']['x'],
            'y': state['pos']['y'],
            'theta': state['theta'],
            'psi': state['psi']
        }
        return out


BILBO_3D_StateSpace_7D.mappings = [Mapping_BILBO_SS_2_CF(), Mapping_CF_2_BILBO_SS()]


# -----------------------------------------------------------------------------
# BILBO DYNAMICS: LINEAR & NONLINEAR MODELS
# -----------------------------------------------------------------------------
class BILBO_2D_Linear:
    """
    Linearized dynamics for the BILBO robot (2D model).
    Converts a continuous-time model to discrete time and computes state-feedback gains.
    """

    def __init__(self, model: BilboModel, Ts, poles=None):
        self.Ts = Ts
        self.model = model
        self.n = 4  # number of states
        self.p = 1
        self.q = 1
        self.K_cont = np.zeros((1, self.n))
        self.K_disc = np.zeros((1, self.n))
        # Compute continuous-time model matrices.
        self.A, self.B, self.C, self.D = self.linear_model()
        self.sys_cont = control.StateSpace(self.A, self.B, self.C, self.D, remove_useless_states=False)
        # Discretize the continuous model.
        self.sys_disc = control.c2d(self.sys_cont, self.Ts)
        self.A_d = np.asarray(self.sys_disc.A)
        self.B_d = np.asarray(self.sys_disc.B)
        self.C_d = np.asarray(self.sys_disc.C)
        self.D_d = np.asarray(self.sys_disc.D)
        if poles is not None:
            self.set_poles(poles)

    def linear_model(self):
        g = 9.81
        model = self.model
        C_21 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * model.m_b * model.l
        V_1 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * (
                model.I_y + model.m_b * model.l ** 2) - model.m_b ** 2 * model.l ** 2
        D_22 = (
                       model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha + model.m_b * model.l * 2 * model.c_alpha / model.r_w
        D_21 = (
                       model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha / model.r_w + model.m_b * model.l * 2 * model.c_alpha / model.r_w ** 2
        C_11 = model.m_b ** 2 * model.l ** 2
        D_12 = (
                       model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w - model.m_b * model.l * 2 * model.c_alpha
        D_11 = (
                       model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w ** 2 - model.m_b * model.l * 2 * model.c_alpha / model.r_w

        A = np.array([
            [0, 1, 0, 0],
            [0, -D_11 / V_1, -C_11 * g / V_1, D_12 / V_1],
            [0, 0, 0, 1],
            [0, D_21 / V_1, C_21 * g / V_1, -D_22 / V_1]
        ])

        B_1 = (model.I_y + model.m_b * model.l ** 2) / model.r_w + model.m_b * model.l
        B_2 = model.m_b * model.l / model.r_w + model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2

        B = np.array([
            [0],
            [B_1 / V_1],
            [0],
            [-B_2 / V_1]
        ])
        C = np.array([[0, 0, 1, 0]])
        D = 0
        return A, B, C, D

    def set_poles(self, poles):
        poles = np.asarray(poles)
        self.K_cont = np.asarray(control.place(self.A, self.B, poles))
        self.K_disc = np.asarray(control.place(self.A_d, self.B_d, np.exp(poles * self.Ts)))
        self.A_hat = self.A - self.B @ self.K_cont
        self.sys_cont = control.StateSpace(self.A_hat, self.B, self.C, self.D, remove_useless_states=False)
        self.A_hat_d = self.A_d - self.B_d @ self.K_disc
        self.sys_disc = control.StateSpace(self.A_hat_d, self.B_d, self.C_d, self.D_d, self.Ts,
                                           remove_useless_states=False)
        return self.K_disc


class BILBO_2D_Nonlinear(core.dynamics.Dynamics):
    """
    Nonlinear dynamics for BILBO based on a 2D model.
    Uses a linearization (BILBO_2D_Linear) for state feedback.
    """
    # Use the 7D state space from the 3D BILBO configuration.
    state_space = BILBO_3D_StateSpace_7D
    input_space = BILBO_2D_InputSpace
    output_space = BILBO_3D_StateSpace_7D

    def __init__(self, model: BilboModel, Ts, poles=None, nominal_model=None):
        self.model = model
        if nominal_model is None:
            self.linear_dynamics = BILBO_2D_Linear(model=model, Ts=Ts, poles=poles)
        else:
            self.linear_dynamics = BILBO_2D_Linear(model=nominal_model, Ts=Ts, poles=poles)
        self.q = 1
        self.p = 1
        self.n = 4
        # Use the 4D state space for the linearization (e.g., BILBO_2D_StateSpace_4D)
        super().__init__(Ts=Ts, state_space=BILBO_2D_StateSpace_4D, input_space=BILBO_2D_InputSpace)
        self.K = self.linear_dynamics.K

    def _dynamics(self, state, input):
        g = 9.81
        s = state[0]
        v = state[1]
        theta = state[2]
        theta_dot = state[3]
        # Compute control deviation
        u = input - self.K @ state

        model = self.model
        C_12 = (model.I_y + model.m_b * model.l ** 2) * model.m_b * model.l
        C_22 = model.m_b ** 2 * model.l ** 2 * np.cos(theta)
        C_21 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * model.m_b * model.l
        V_1 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * (
                model.I_y + model.m_b * model.l ** 2) - model.m_b ** 2 * model.l ** 2 * np.cos(theta) ** 2
        D_22 = (
                       model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha + model.m_b * model.l * np.cos(
            theta) * 2 * model.c_alpha / model.r_w
        D_21 = (
                       model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha / model.r_w + model.m_b * model.l * np.cos(
            theta) * 2 * model.c_alpha / model.r_w ** 2
        C_11 = model.m_b ** 2 * model.l ** 2 * np.cos(theta)
        D_12 = (model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w - model.m_b * model.l * np.cos(
            theta) * 2 * model.c_alpha
        D_11 = (
                       model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w ** 2 - 2 * model.m_b * model.l * np.cos(
            theta) * model.c_alpha / model.r_w
        B_2 = model.m_b * model.l / model.r_w * np.cos(
            theta) + model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2
        B_1 = (model.I_y + model.m_b * model.l ** 2) / model.r_w + model.m_b * model.l * np.cos(theta)
        C_31 = 2 * (model.I_z - model.I_x - model.m_b * model.l ** 2) * np.cos(theta)
        C_32 = model.m_b * model.l
        D_33 = model.d_w ** 2 / (2 * model.r_w ** 2) * model.c_alpha
        V_2 = model.I_z + 2 * model.I_w2 + (model.m_w + model.I_w / model.r_w ** 2) * model.d_w ** 2 / 2 - (
                model.I_z - model.I_x - model.m_b * model.l ** 2) * np.sin(theta) ** 2
        B_3 = model.d_w / (2 * model.r_w)
        C_13 = (model.I_y + model.m_b * model.l ** 2) * model.m_b * model.l + model.m_b * model.l * (
                model.I_z - model.I_x - model.m_b * model.l ** 2) * np.cos(theta) ** 2
        C_23 = (model.m_b ** 2 * model.l ** 2 + (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * (
                model.I_z - model.I_x - model.m_b * model.l ** 2)) * np.cos(theta)

        state_dot = np.zeros(self.n)
        state_dot[0] = v
        state_dot[1] = (np.sin(theta) / V_1) * (-C_11 * g + C_12 * theta_dot ** 2) - (D_11 / V_1) * v + (
                D_12 / V_1) * theta_dot + (B_1 / V_1) * u[0] - model.tau_x * v
        state_dot[2] = theta_dot
        state_dot[3] = (np.sin(theta) / V_1) * (C_21 * g - C_22 * theta ** 2) + (D_21 / V_1) * v - (
                D_22 / V_1) * theta_dot - (B_2 / V_1) * u[0] - model.tau_theta * theta_dot
        state = state + state_dot * self.Ts
        return state

    def _output_function(self, state):
        return state['theta']


class BILBO_3D_Linear(core.dynamics.LinearDynamics):
    """
    Linear dynamics for BILBO in 3D.
    Computes a discrete-time state-feedback controller.
    """
    state_space = BILBO_3D_StateSpace_6D()
    input_space = BILBO_3D_InputSpace()
    output_space = BILBO_3D_StateSpace_6D()

    def __init__(self, model: BilboModel, Ts, poles=None, ev=None):
        self.model = model
        self.Ts = Ts
        A_cont, B_cont, C_cont, D_cont = self._linear_model()
        self.sys_cont = control.StateSpace(A_cont, B_cont, C_cont, D_cont, remove_useless_states=False)
        sys_disc = control.c2d(self.sys_cont, Ts)
        self.A = sys_disc.A
        self.B = sys_disc.B
        self.C = sys_disc.C
        self.D = sys_disc.D
        super().__init__(Ts=Ts)
        if poles is not None and ev is None:
            self.K = self.set_poles(poles)
        elif poles is not None and ev is not None:
            self.K = self.set_eigenstructure(poles, ev)
        else:
            self.K = np.zeros((self.p, self.n))

    def _linear_model(self):
        g = 9.81
        model = self.model
        C_21 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * model.m_b * model.l
        V_1 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * (
                model.I_y + model.m_b * model.l ** 2) - model.m_b ** 2 * model.l ** 2
        D_22 = (
                       model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha + model.m_b * model.l * 2 * model.c_alpha / model.r_w
        D_21 = (
                       model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha / model.r_w + model.m_b * model.l * 2 * model.c_alpha / model.r_w ** 2
        C_11 = model.m_b ** 2 * model.l ** 2
        D_12 = (
                       model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w - model.m_b * model.l * 2 * model.c_alpha
        D_11 = (
                       model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w ** 2 - model.m_b * model.l * 2 * model.c_alpha / model.r_w
        D_33 = model.d_w / (2 * model.r_w ** 2) * model.c_alpha
        V_2 = model.I_z + 2 * model.I_w2 + (model.m_w + model.I_w / model.r_w ** 2) * model.d_w ** 2 / 2
        A = np.array([
            [0, 1, 0, 0, 0, 0],
            [0, -D_11 / V_1, -C_11 * g / V_1, D_12 / V_1, 0, 0],
            [0, 0, 0, 1, 0, 0],
            [0, D_21 / V_1, C_21 * g / V_1, -D_22 / V_1, 0, 0],
            [0, 0, 0, 0, 0, 1],
            [0, 0, 0, 0, 0, -D_33 / V_2]
        ])
        B_1 = (model.I_y + model.m_b * model.l ** 2) / model.r_w + model.m_b * model.l
        B_2 = model.m_b * model.l / model.r_w + model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2
        B_3 = model.d_w / (2 * model.r_w)
        B = np.array([
            [0, 0],
            [B_1 / V_1, B_1 / V_1],
            [0, 0],
            [-B_2 / V_1, -B_2 / V_1],
            [0, 0],
            [-B_3 / V_2, B_3 / V_2]
        ])
        C = np.array([[0, 0, 1, 0, 0, 0]])
        D = [0, 0]
        return A, B, C, D

    def set_poles(self, poles):
        poles = np.asarray(poles)
        self.K = np.asarray(control.place(self.A, self.B, np.exp(poles * self.Ts)))
        A_hat = self.A - self.B @ self.K
        self.A = A_hat
        self.sys = control.StateSpace(self.A, self.B, self.C, self.D, self.Ts, remove_useless_states=False)
        if hasattr(self, 'sys_cont') and self.sys_cont is not None:
            K = np.asarray(control.place(self.sys_cont.A, self.sys_cont.B, poles))
            self.sys_cont = control.StateSpace((self.sys_cont.A - self.sys_cont.B @ K), self.sys_cont.B,
                                               self.sys_cont.C, self.sys_cont.D, remove_useless_states=False)
        return self.K

    def set_eigenstructure(self, poles, ev, set=True):
        poles = np.asarray(poles)
        K = lib_control.eigenstructure_assignment(self.A, self.B, np.exp(poles * self.Ts), ev)
        if set:
            self.K = K
            A_hat = self.A - self.B @ self.K
            self.A = A_hat
            self.sys = control.StateSpace(self.A, self.B, self.C, self.D, self.Ts, remove_useless_states=False)
        return K


class BILBO_Dynamics_3D(core.dynamics.Dynamics):
    """
    3D dynamics for BILBO.
    This model uses a 7-dimensional state and accepts 2 inputs.
    """
    state_space = BILBO_3D_StateSpace_7D()
    input_space = BILBO_3D_InputSpace()
    output_space = BILBO_3D_StateSpace_7D()

    def __init__(self, model: BilboModel, Ts, poles=None, eigenvectors=None, speed_control: bool = False, *args,
                 **kwargs):

        super().__init__(Ts=Ts, *args, **kwargs)
        self.model = model
        # Limit the pitch (theta) to the maximum allowed value from the model.
        self.state_space['theta'].limits = [-self.model.max_pitch, self.model.max_pitch]
        self.q = 1
        self.p = 2
        self.n = 7

    def update(self, input=None):
        if input is not None:
            self.input = input
        self.state = self._dynamics(self.state, self.input)

    def _dynamics(self, state, input):
        g = 9.81
        x = state[0].value
        y = state[1].value
        v = state[2].value
        theta = state[3].value
        theta_dot = state[4].value
        psi = state[5].value
        psi_dot = state[6].value
        u = [input[0].value, input[1].value]
        model = self.model
        C_12 = (model.I_y + model.m_b * model.l ** 2) * model.m_b * model.l
        C_22 = model.m_b ** 2 * model.l ** 2 * np.cos(theta)
        C_21 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * model.m_b * model.l
        V_1 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * (
                model.I_y + model.m_b * model.l ** 2) - model.m_b ** 2 * model.l ** 2 * np.cos(theta) ** 2
        D_22 = (
                       model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha + model.m_b * model.l * np.cos(
            theta) * 2 * model.c_alpha / model.r_w
        D_21 = (
                       model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha / model.r_w + model.m_b * model.l * np.cos(
            theta) * 2 * model.c_alpha / model.r_w ** 2
        C_11 = model.m_b ** 2 * model.l ** 2 * np.cos(theta)
        D_12 = (model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w - model.m_b * model.l * np.cos(
            theta) * 2 * model.c_alpha
        D_11 = (
                       model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w ** 2 - 2 * model.m_b * model.l * np.cos(
            theta) * model.c_alpha / model.r_w
        B_2 = model.m_b * model.l / model.r_w * np.cos(
            theta) + model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2
        B_1 = (model.I_y + model.m_b * model.l ** 2) / model.r_w + model.m_b * model.l * np.cos(theta)
        C_31 = 2 * (model.I_z - model.I_x - model.m_b * model.l ** 2) * np.cos(theta)
        C_32 = model.m_b * model.l
        D_33 = model.d_w ** 2 / (2 * model.r_w ** 2) * model.c_alpha
        V_2 = model.I_z + 2 * model.I_w2 + (model.m_w + model.I_w / model.r_w ** 2) * model.d_w ** 2 / 2 - (
                model.I_z - model.I_x - model.m_b * model.l ** 2) * np.sin(theta) ** 2
        B_3 = model.d_w / (2 * model.r_w)
        C_13 = (model.I_y + model.m_b * model.l ** 2) * model.m_b * model.l + model.m_b * model.l * (
                model.I_z - model.I_x - model.m_b * model.l ** 2) * np.cos(theta) ** 2
        C_23 = (model.m_b ** 2 * model.l ** 2 + (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * (
                model.I_z - model.I_x - model.m_b * model.l ** 2)) * np.cos(theta)
        state_dot = np.zeros(self.n)
        state_dot[0] = v * np.cos(psi)
        state_dot[1] = v * np.sin(psi)
        state_dot[2] = (np.sin(theta) / V_1) * (-C_11 * g + C_12 * theta_dot ** 2 + C_13 * psi_dot ** 2) - (
                D_11 / V_1) * v + (D_12 / V_1) * theta_dot + (B_1 / V_1) * (u[0] + u[1]) - model.tau_x * v
        state_dot[3] = theta_dot
        state_dot[4] = (np.sin(theta) / V_1) * (C_21 * g - C_22 * theta ** 2 - C_23 * psi_dot ** 2) + (
                D_21 / V_1) * v - (D_22 / V_1) * theta_dot - (B_2 / V_1) * (
                               u[0] + u[1]) - model.tau_theta * theta_dot
        state_dot[5] = psi_dot
        state_dot[6] = (np.sin(theta) / V_2) * (C_31 * theta_dot * psi_dot - C_32 * psi_dot * v) - (
                D_33 / V_2) * psi_dot - (B_3 / V_2) * (u[0] - u[1])
        state = state + state_dot * self.Ts
        return state

    def _output(self, state):
        return state['theta']

    def _init(self):
        ...


# -----------------------------------------------------------------------------
# BILBO AGENTS
# -----------------------------------------------------------------------------
class BILBO_Agent(core.agents.Agent):
    """
    Base agent for BILBO.
    """
    object_type: str = 'bilbo_agent'
    space = Space3D_BILBO()

    def __init__(self, world, agent_id, *args, **kwargs):
        # Set unique id (do not use "name")
        self.id = f"BILBO_{agent_id}"
        super().__init__(world=world, agent_id=agent_id, *args, **kwargs)
        self.physics: BILBO_PhysicalObject = BILBO_PhysicalObject()

    def _getParameters(self):
        params = super()._getParameters()
        params['physics'] = {}
        params['size'] = {
            'x': self.physics.depth,
            'y': self.physics.width,
            'z': self.physics.height
        }
        params['physics']['size'] = [self.physics.depth, self.physics.width, self.physics.height]
        params['physics']['wheel_diameter'] = self.physics.wheel_diameter
        params['physics']['l_w'] = self.physics.l_w
        return params

    def _getSample(self):
        sample = super()._getSample()
        sample['collision_box_pos'] = {
            'x': self.physics.bounding_objects['body'].position[0],
            'y': self.physics.bounding_objects['body'].position[1],
            'z': self.physics.bounding_objects['body'].position[2]
        }
        return sample

    def _init(self, *args, **kwargs):
        self._updatePhysics()


class BILBO_DynamicAgent(BILBO_Agent, core.agents.DynamicAgent):
    """
    Dynamic agent for BILBO that incorporates control and feedback.
    """
    object_type: str = 'bilbo_agent'
    space = Space3D_BILBO()
    dynamics_class = BILBO_Dynamics_3D

    # The input_space will be selected based on whether speed control is enabled.
    Ts = DEFAULT_SAMPLE_TIME

    def __init__(self, world, agent_id, speed_control: bool = False, poles=None, eigenvectors=None,
                 model: BilboModel = DEFAULT_BILBO_MODEL, *args, **kwargs):
        if poles is None:
            # Default poles for BILBO 3D (example values)
            poles = [0, -20, -3 + 1j, -3 - 1j, 0, -1.5]
        # Instantiate dynamics with provided sample time and model.
        self.dynamics = self.dynamics_class(Ts=self.Ts, model=model)
        super().__init__(world=world, agent_id=agent_id, *args, **kwargs)

        if speed_control:
            self.controller_v = lib_control.PID_ctrl(Ts=self.Ts, P=-1.534 / 2, I=-2.81 / 2, D=-0.07264 / 2, max_rate=75)
            self.controller_psidot = lib_control.PID_ctrl(Ts=self.Ts, P=-0.3516, I=-1.288, D=-0.0002751)
            self.input_space = BILBO_3D_ExternalInputSpace()
        else:
            self.controller_v = None
            self.controller_psidot = None
            self.input_space = BILBO_3D_InputSpace()
        self.linear_dynamics = BILBO_3D_Linear(self.dynamics.model, self.Ts, poles, eigenvectors)
        # Combine a zero column with the computed gain matrix.
        self.state_ctrl_K = np.hstack((np.zeros((2, 1)), self.linear_dynamics.K))
        self.input = self.input_space.getState()
        core.scheduling.Action(action_id='logic', object=self, function=self._controller)

    def _controller(self, input=None):
        if input is not None:
            self.input = input
        if self.controller_v is not None and self.controller_psidot is not None:
            e_v = self.input['v'] - self.dynamics.state['v']
            u_v = self.controller_v.updateConfig(e_v.value)
            e_psidot = self.input['psi_dot'] - self.dynamics.state['psi_dot']
            u_psidot = self.controller_psidot.updateConfig(e_psidot.value)
            input_dynamics = self.dynamics.input_space.map([u_v + u_psidot, u_v - u_psidot])
        else:
            input_dynamics = self.input
        input_dynamics = input_dynamics - self.state_ctrl_K @ self.state
        self.dynamics.input = input_dynamics

    @property
    def input(self):
        return self._input

    @input.setter
    def input(self, value: (list, np.ndarray, core.spaces.State)):
        self._input = self.input_space.map(value)

    def _getParameters(self):
        params = super()._getParameters()
        params['physics'] = {}
        params['size'] = {
            'x': self.physics.depth,
            'y': self.physics.width,
            'z': self.physics.height
        }
        params['physics']['size'] = [self.physics.depth, self.physics.width, self.physics.height]
        params['physics']['wheel_diameter'] = self.physics.wheel_diameter
        params['physics']['l_w'] = self.physics.l_w
        return params

    def _getSample(self):
        sample = super()._getSample()
        return sample

    def _init(self, *args, **kwargs):
        self._updatePhysics()

    def _action_control(self):
        # Placeholder for additional control actions if needed.
        pass


# -----------------------------------------------------------------------------
# BILBO ILC AGENT (ITERATIVE LEARNING CONTROL)
# -----------------------------------------------------------------------------
class BILBO_ILC_Agent(BILBO_DynamicAgent):
    """
    BILBO agent that implements Iterative Learning Control (ILC) over a series of trials.
    """
    # Reference trajectory and trial-related variables.
    reference: np.ndarray  # Reference trajectory (desired output)
    K: int  # Length of the reference trajectory
    j: int  # Current trial number
    k: int  # Current sample index within the trial
    u_j: np.ndarray  # Current input trajectory for the trial
    y_j: np.ndarray  # Measured output trajectory
    e_j: np.ndarray  # Error trajectory
    trials: list  # List to store data from previous trials
    J_max: int = 20  # Maximum number of trials
    initial_state: core.spaces.State  # Initial state for each trial

    collision_during_trial: bool
    L: np.ndarray  # Learning matrix
    Q: np.ndarray  # Q filter matrix
    wait_steps: int
    trial_state: str  # 'trial', 'wait_before_trial', or 'wait_after_trial'
    learning_finished_flag: bool
    learning_successful: bool
    dynamics_2d_linear: BILBO_2D_Linear

    def __init__(self, world, agent_id, reference: np.ndarray, wait_steps: int = 50,
                 r: float = 0.001, s: float = 0.1, initial_state: list = None,
                 *args, **kwargs):
        super().__init__(world=world, agent_id=agent_id)
        self.reference = np.asarray(reference)
        self.K = len(self.reference)
        self.j = 0
        self.k = 0
        # Initialize input trajectory with random noise.
        self.u_j = np.random.normal(0, scale=1, size=self.reference.shape)
        self.y_j = np.zeros_like(self.reference)
        self.wait_steps = wait_steps
        self.collision_during_trial = False
        self.trials = []
        self.r = r
        self.s = s
        if initial_state is None:
            initial_state = [-0.35, 0, 0, 0, 0, 0, 0]
        self.initial_state = self.dynamics.state_space.map(initial_state)
        self.state = self.initial_state
        self.trial_state = 'wait_before_trial'
        self.learning_finished_flag = False
        self.learning_successful = False
        # Instantiate the 2D linear model for ILC using provided model parameters.
        self.dynamics_2d_linear = BILBO_2D_Linear(model=DEFAULT_BILBO_MODEL, Ts=DEFAULT_SAMPLE_TIME,
                                                  poles=[0, -20, -3 + 1j, -3 - 1j])
        self.setILC(r, s)
        core.scheduling.Action(id='input', object=self, function=self._action_input)
        core.scheduling.Action(id='logic2', object=self, function=self.update_after_step)

    def setILC(self, r, s):
        # Calculate the transition matrix using the discrete-time linear model.
        P = lib_control.calc_transition_matrix(self.dynamics_2d_linear.sys_disc, self.K)
        Qw = np.eye(self.K)
        Rw = r * np.eye(self.K)
        Sw = s * np.eye(self.K)
        self.Q, self.L = lib_control.qlearning(P, Qw, Rw, Sw)

    def update_after_step(self):
        if self.k == self.K - 1:
            self.update_after_trial()
        else:
            self.y_j[self.k] = self.state['theta'].value
            if self.trial_state == 'trial':
                self.collision_during_trial = self.collision_during_trial or self.physics.collision.collision_state
                if self.collision_during_trial:
                    setBabylonSettings(background_color=[242 / 255, 56 / 255, 56 / 255])
            self.k += 1

    def update_after_trial(self):
        if self.learning_finished_flag:
            return
        # Compute error signal.
        self.e_j = self.reference - self.y_j
        # Save trial data.
        self.trials.append({
            'u': copy.copy(self.u_j),
            'y': copy.copy(self.y_j),
            'e': copy.copy(self.e_j),
            'e_norm': np.linalg.norm(self.e_j),
            'collision': self.collision_during_trial
        })
        # Check for successful trial.
        if not self.collision_during_trial and self.state['x'].value > 0.0:
            self.learning_finished_flag = True
            self.learning_successful = True
            setBabylonSettings(status=f"Trial {self.j}: Learning successful")
            setBabylonSettings(background_color=[29 / 255, 145 / 255, 31 / 255])
            save_data = {
                'trials': self.trials,
                'reference': self.reference,
                's': self.s,
                'r': self.r,
                'success': self.learning_successful
            }
            with open("ilc_data.p", "wb") as filehandler:
                pickle.dump(save_data, filehandler)
        if self.j == self.J_max - 1:
            # Maximum trials reached; mark failure.
            self.learning_finished_flag = True
            self.learning_successful = False
            plt.plot(self.trials[-1]['y'])
            plt.plot(self.reference)
            setBabylonSettings(status=f"Trial {self.j}: Learning failed")
            save_data = {
                'trials': self.trials,
                'reference': self.reference,
                's': self.s,
                'r': self.r,
                'success': self.learning_successful
            }
            with open("ilc_data.p", "wb") as filehandler:
                pickle.dump(save_data, filehandler)
        # Update the input trajectory using the ILC update law.
        self.u_j = self.Q @ (self.u_j + self.L @ self.e_j)
        self.j += 1
        self.trial_state = 'wait_after_trial'
        self.collision_during_trial = False
        self.k = 0

    def _action_input(self):
        print("INPUT")
        if not self.learning_finished_flag:
            if self.trial_state == 'trial':
                self.input = [self.u_j[self.k] / 2, self.u_j[self.k] / 2]
            elif self.trial_state in ('wait_after_trial', 'wait_before_trial'):
                self.input = [0, 0]
        else:
            self.input = [0, 0]

    def _action_entry(self, *args, **kwargs):
        super()._action_entry(*args, **kwargs)
        if self.j == 0:
            setBabylonSettings(status="Trial 0")
        if not self.learning_finished_flag:
            if self.trial_state == 'wait_before_trial' and self.k == self.wait_steps:
                self.k = 0
                self.trial_state = 'trial'
            elif self.trial_state == 'wait_after_trial' and self.k == self.wait_steps:
                self.k = 0
                self.trial_state = 'wait_before_trial'
                self.state = copy.copy(self.initial_state)
                self.setPosition(x=self.state['x'])
                setBabylonSettings(status=f"Trial {self.j}")
                setBabylonSettings(background_color=0)

    def _action_exit(self, *args, **kwargs):
        super()._action_exit(*args, **kwargs)
