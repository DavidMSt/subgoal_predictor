# import copy
# import dataclasses
# import enum
# import math
# import pickle
#
# import control
# import matplotlib.pyplot as plt
# import numpy as np
# from numpy import nan, hstack
#
# from extensions.simulation.src import core as core
# from extensions.simulation.src.core import spaces as sp
# from extensions.simulation.src.core.dynamics import LinearDynamics
# from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS
# from extensions.simulation.src.utils import lib_control
# from extensions.simulation.src.utils.orientations import twiprToRotMat, twiprFromRotMat
#
# DEFAULT_SAMPLE_TIME = 0.01
#
#
# @dataclasses.dataclass
# class BilboModel:
#     """
#     Dataclass for the two-wheeled (BILBO) robot model parameters.
#     """
#     m_b: float
#     m_w: float
#     l: float
#     d_w: float
#     I_w: float
#     I_y: float
#     I_x: float
#     I_z: float
#     c_alpha: float
#     r_w: float
#     tau_theta: float
#     tau_x: float
#     max_pitch: float
#
#
# # Default model parameters (formerly TWIPR_Michael_Model)
# # DEFAULT_BILBO_MODEL = BilboModel(
# #     m_b=2.5,
# #     m_w=0.636,
# #     l=0.026,
# #     d_w=0.28,
# #     I_w=5.1762e-4,
# #     I_y=0.01648,
# #     I_x=0.02,
# #     I_z=0.03,
# #     c_alpha=4.6302e-4,
# #     r_w=0.055,
# #     tau_theta=0.0,
# #     tau_x=0.0,
# #     max_pitch=np.deg2rad(105)
# # )
#
#
# DEFAULT_BILBO_MODEL = BilboModel(
#     m_b=1.2,
#     m_w=0.4,
#     l=0.026,
#     d_w=0.22,
#     I_w=2e-4,
#     I_y=0.005,
#     I_x=0.02,
#     I_z=0.03,
#     c_alpha=4.6302e-4,
#     r_w=0.06,
#     tau_theta=0.4,
#     tau_x=0.4,
#     max_pitch=np.deg2rad(105)
# )
#
# # Default model parameters (formerly TWIPR_Michael_Model)
# BILBO_SMALL = BilboModel(
#     m_b=1,
#     m_w=0.292,
#     l=0.01,
#     d_w=0.168,
#     I_w=2.773e-4,
#     I_y=0.001,
#     I_x=0.01,
#     I_z=0.03,
#     c_alpha=4.6302e-4,
#     r_w=0.062,
#     tau_theta=0.5,
#     tau_x=0.5,
#     max_pitch=np.deg2rad(105)
# )
#
# BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES = [0, -10, -5 + 3j, -5 - 3j, 0, -15]
#
#
# BILBO_2D_POLES = [0, -10, -5 + 3j, -5 - 3j]
#
# BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS = np.array([[1, nan, nan, nan, 0, nan],
#                                                           [nan, 1, nan, nan, nan, nan],
#                                                           [nan, nan, 1, 1, nan, 0],
#                                                           [nan, nan, nan, nan, nan, nan],
#                                                           [0, nan, nan, nan, 1, 1],
#                                                           [nan, 0, 0, 0, nan, nan]])
#
#
# # === SPACES ===========================================================================================================
# class Space3D_BILBO(core.spaces.Space):
#     """
#     3D space for BILBO.
#     Consists of a 2D position vector and two scalar angles.
#     """
#     dimensions = [
#         core.spaces.VectorDimension(name='pos', base_type=core.spaces.PositionVector2D),
#         core.spaces.ScalarDimension(name='theta', limits=[-math.pi, math.pi], wrapping=True),
#         core.spaces.ScalarDimension(name='psi', limits=[0, 2 * math.pi], wrapping=True)
#     ]
#
#     def _add(self, state1, state2, new_state):
#         raise Exception("Addition not allowed in Space3D_BILBO")
#
#
# class Mapping_BILBO_2_3D(core.spaces.SpaceMapping):
#     """
#     Mapping from Space3D_BILBO to the standard 3D space.
#     """
#     space_to = core.spaces.Space3D
#     space_from = Space3D_BILBO
#
#     def _map(self, state):
#         out = {
#             'pos': [state['pos']['x'], state['pos']['y'], 0],
#             'ori': twiprToRotMat(state['theta'].value, state['psi'].value)
#         }
#         return out
#
#
# class Mapping_3D_2_BILBO(core.spaces.SpaceMapping):
#     """
#     Mapping from the standard 3D space to Space3D_BILBO.
#     """
#     space_from = core.spaces.Space3D
#     space_to = Space3D_BILBO
#
#     def _map(self, state):
#         angles = twiprFromRotMat(state['ori'].value)
#         out = {
#             'pos': [state['pos']['x'], state['pos']['y']],
#             'theta': angles[1],
#             'psi': angles[0]
#         }
#         return out
#
#
# # Register mappings
# Space3D_BILBO.mappings = [Mapping_3D_2_BILBO(), Mapping_BILBO_2_3D()]
# core.spaces.Space3D.mappings.append(Mapping_3D_2_BILBO())
#
#
# class BILBO_PhysicalObject(core.physics.PhysicalBody):
#     """
#     Physical representation for BILBO.
#     """
#
#     def __init__(self, height: float = 0.174, width: float = 0.126, depth: float = 0.064,
#                  wheel_diameter: float = 0.13, l_w: float = 0.056, *args, **kwargs):
#         super().__init__()
#         self.height = height
#         self.width = width
#         self.depth = depth
#         self.wheel_diameter = wheel_diameter
#         self.l_w = l_w
#         self.bounding_objects = {
#             'body': core.physics.CuboidPrimitive(
#                 size=[self.depth, self.width, self.height],
#                 position=[0, 0, 0],
#                 orientation=np.eye(3)
#             )
#         }
#         self.proximity_sphere.radius = self._getProximitySphereRadius()
#
#     def update(self, config, *args, **kwargs):
#         v_t = [config['pos']['x'], config['pos']['y'], self.wheel_diameter / 2]
#         v_m = [0, 0, self.height / 2 - self.l_w]
#         # Multiply vector v_m by orientation (assumed to be a matrix)
#         v_m_e = config['ori'] * v_m
#         new_position = v_t + v_m_e
#         self.bounding_objects['body'].update(new_position, config['ori'].value)
#         self._calcProximitySphere()
#
#     def _calcProximitySphere(self):
#         self.proximity_sphere.radius = self._getProximitySphereRadius()
#         self.proximity_sphere.update(position=self.bounding_objects['body'].position)
#
#     def _getProximitySphereRadius(self):
#         return (self.height / 2) * 1.1
#
#
# # Define several state and input spaces for BILBO.
# class BILBO_2D_InputSpace(core.spaces.Space):
#     dimensions = [core.spaces.ScalarDimension(name='M')]
#
#
# class BILBO_2D_StateSpace_4D(core.spaces.Space):
#     dimensions = [
#         core.spaces.ScalarDimension(name='s'),
#         core.spaces.ScalarDimension(name='v'),
#         core.spaces.ScalarDimension(name='theta'),
#         core.spaces.ScalarDimension(name='theta_dot')
#     ]
#
#
# class BILBO_2D_StateSpace_5D(core.spaces.Space):
#     dimensions = [
#         core.spaces.ScalarDimension(name='x'),
#         core.spaces.ScalarDimension(name='y'),
#         core.spaces.ScalarDimension(name='v'),
#         core.spaces.ScalarDimension(name='theta'),
#         core.spaces.ScalarDimension(name='theta_dot')
#     ]
#
#
# class BILBO_3D_InputSpace(core.spaces.Space):
#     dimensions = [
#         core.spaces.ScalarDimension(name='M_L'),
#         core.spaces.ScalarDimension(name='M_R')
#     ]
#
#
# class BILBO_3D_VelocityInputSpace(core.spaces.Space):
#     dimensions = [
#         core.spaces.ScalarDimension(name='v'),
#         core.spaces.ScalarDimension(name='psi_dot')
#     ]
#
#
# class BILBO_3D_StateSpace_6D(core.spaces.Space):
#     dimensions = [
#         core.spaces.ScalarDimension(name='s'),
#         core.spaces.ScalarDimension(name='v'),
#         core.spaces.ScalarDimension(name='theta'),
#         core.spaces.ScalarDimension(name='theta_dot'),
#         core.spaces.ScalarDimension(name='psi'),
#         core.spaces.ScalarDimension(name='psi_dot')
#     ]
#
#
# class BILBO_3D_StateSpace_7D(core.spaces.Space):
#     dimensions = [
#         core.spaces.ScalarDimension(name='x'),
#         core.spaces.ScalarDimension(name='y'),
#         core.spaces.ScalarDimension(name='v'),
#         core.spaces.ScalarDimension(name='theta', wrapping=False),
#         core.spaces.ScalarDimension(name='theta_dot'),
#         core.spaces.ScalarDimension(name='psi'),
#         core.spaces.ScalarDimension(name='psi_dot')
#     ]
#
#
# class Mapping_BILBO_SS_2_CF(core.spaces.SpaceMapping):
#     """
#     Mapping from BILBO state space (7D) to configuration space (Space3D_BILBO).
#     """
#     space_from = BILBO_3D_StateSpace_7D
#     space_to = Space3D_BILBO
#
#     def _map(self, state):
#         out = {
#             'pos': [state['x'], state['y']],
#             'theta': state['theta'],
#             'psi': state['psi']
#         }
#         return out
#
#
# class Mapping_CF_2_BILBO_SS(core.spaces.SpaceMapping):
#     """
#     Mapping from configuration space (Space3D_BILBO) to BILBO state space (7D).
#     """
#     space_from = Space3D_BILBO
#     space_to = BILBO_3D_StateSpace_7D
#
#     def _map(self, state):
#         out = {
#             'x': state['pos']['x'],
#             'y': state['pos']['y'],
#             'theta': state['theta'],
#             'psi': state['psi']
#         }
#         return out
#
#
# BILBO_3D_StateSpace_7D.mappings = [Mapping_BILBO_SS_2_CF(), Mapping_CF_2_BILBO_SS()]
#
#
# # -----------------------------------------------------------------------------
# # BILBO DYNAMICS: LINEAR & NONLINEAR MODELS
# # -----------------------------------------------------------------------------
# class BILBO_Dynamics_2D_Linear(LinearDynamics):
#     input_space = BILBO_2D_InputSpace
#     state_space = BILBO_2D_StateSpace_4D
#     output_space = BILBO_2D_StateSpace_4D
#
#     # === INIT =========================================================================================================
#     def __init__(self, model: BilboModel, Ts, poles=None):
#         self.Ts = Ts
#
#         super().__init__(Ts)
#
#         if poles is None:
#             poles = BILBO_2D_POLES
#
#         self.model = model
#         self.n = 4  # number of states
#         self.p = 1
#         self.q = 1
#
#         self.K_cont = np.zeros((1, self.n))
#         self.K_disc = np.zeros((1, self.n))
#
#         # Compute continuous-time model matrices.
#         self.A, self.B, self.C, self.D = self._getLinearModel()
#         self.sys_cont = control.StateSpace(self.A, self.B, self.C, self.D, remove_useless_states=False)
#
#         self.sys_cont_controlled = None
#
#         # Discretize the continuous model.
#         self.sys = control.c2d(self.sys_cont, self.Ts)
#         self.sys_controlled = None
#
#         self.A_d = np.asarray(self.sys.A)
#         self.B_d = np.asarray(self.sys.B)
#         self.C_d = np.asarray(self.sys.C)
#         self.D_d = np.asarray(self.sys.D)
#         if poles is not None:
#             self.setPoles(poles)
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def setPoles(self, poles):
#         poles = np.asarray(poles)
#         self.K_cont = np.asarray(control.place(self.A, self.B, poles))
#         self.K_disc = np.asarray(control.place(self.A_d, self.B_d, np.exp(poles * self.Ts)))
#
#         self.A_hat = self.A - self.B @ self.K_cont
#         self.sys_cont_controlled = control.StateSpace(self.A_hat, self.B, self.C, self.D, remove_useless_states=False)
#
#         self.A_hat_d = self.A_d - self.B_d @ self.K_disc
#         self.sys_controlled = control.StateSpace(self.A_hat_d, self.B_d, self.C_d, self.D_d, self.Ts,
#                                                  remove_useless_states=False)
#         return self.K_disc
#
#     # ------------------------------------------------------------------------------------------------------------------
#     # ------------------------------------------------------------------------------------------------------------------
#     def _getLinearModel(self):
#         g = 9.81
#         model = self.model
#         C_21 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * model.m_b * model.l
#         V_1 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * (
#                 model.I_y + model.m_b * model.l ** 2) - model.m_b ** 2 * model.l ** 2
#         D_22 = (
#                        model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha + model.m_b * model.l * 2 * model.c_alpha / model.r_w
#         D_21 = (
#                        model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha / model.r_w + model.m_b * model.l * 2 * model.c_alpha / model.r_w ** 2
#         C_11 = model.m_b ** 2 * model.l ** 2
#         D_12 = (
#                        model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w - model.m_b * model.l * 2 * model.c_alpha
#         D_11 = (
#                        model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w ** 2 - model.m_b * model.l * 2 * model.c_alpha / model.r_w
#
#         A = np.array([
#             [0, 1, 0, 0],
#             [0, -D_11 / V_1, -C_11 * g / V_1, D_12 / V_1],
#             [0, 0, 0, 1],
#             [0, D_21 / V_1, C_21 * g / V_1, -D_22 / V_1]
#         ])
#
#         B_1 = (model.I_y + model.m_b * model.l ** 2) / model.r_w + model.m_b * model.l
#         B_2 = model.m_b * model.l / model.r_w + model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2
#
#         B = np.array([
#             [0],
#             [B_1 / V_1],
#             [0],
#             [-B_2 / V_1]
#         ])
#         C = np.array([[0, 0, 1, 0]])
#         D = 0
#         return A, B, C, D
#
#
# class BILBO_Dynamics_2D(core.dynamics.Dynamics):
#     # Use the 7D state space from the 3D BILBO configuration.
#     state_space = BILBO_2D_StateSpace_4D()
#     input_space = BILBO_2D_InputSpace()
#     output_space = BILBO_2D_StateSpace_4D()
#
#     def __init__(self, model: BilboModel, Ts, poles=None, nominal_model=None):
#         super().__init__(Ts=Ts)
#         self.model = model
#
#         # if nominal_model is None:
#         #     self.linear_dynamics = BILBO_2D_Linear(model=model, Ts=Ts, poles=poles)
#         # else:
#         #     self.linear_dynamics = BILBO_2D_Linear(model=nominal_model, Ts=Ts, poles=poles)
#         # self.q = 1
#         # self.p = 1
#         # self.n = 4
#         #
#
#         # self.K = self.linear_dynamics.K
#
#     def _dynamics(self, state, input):
#         g = 9.81
#         s = state[0]
#         v = state[1]
#         theta = state[2]
#         theta_dot = state[3]
#         # Compute control deviation
#         u = input - self.K @ state
#
#         model = self.model
#         C_12 = (model.I_y + model.m_b * model.l ** 2) * model.m_b * model.l
#         C_22 = model.m_b ** 2 * model.l ** 2 * np.cos(theta)
#         C_21 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * model.m_b * model.l
#         V_1 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * (
#                 model.I_y + model.m_b * model.l ** 2) - model.m_b ** 2 * model.l ** 2 * np.cos(theta) ** 2
#         D_22 = (
#                        model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha + model.m_b * model.l * np.cos(
#             theta) * 2 * model.c_alpha / model.r_w
#         D_21 = (
#                        model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha / model.r_w + model.m_b * model.l * np.cos(
#             theta) * 2 * model.c_alpha / model.r_w ** 2
#         C_11 = model.m_b ** 2 * model.l ** 2 * np.cos(theta)
#         D_12 = (model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w - model.m_b * model.l * np.cos(
#             theta) * 2 * model.c_alpha
#         D_11 = (
#                        model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w ** 2 - 2 * model.m_b * model.l * np.cos(
#             theta) * model.c_alpha / model.r_w
#         B_2 = model.m_b * model.l / model.r_w * np.cos(
#             theta) + model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2
#         B_1 = (model.I_y + model.m_b * model.l ** 2) / model.r_w + model.m_b * model.l * np.cos(theta)
#         C_31 = 2 * (model.I_z - model.I_x - model.m_b * model.l ** 2) * np.cos(theta)
#         C_32 = model.m_b * model.l
#         D_33 = model.d_w ** 2 / (2 * model.r_w ** 2) * model.c_alpha
#         V_2 = model.I_z + 2 * model.I_w + (model.m_w + model.I_w / model.r_w ** 2) * model.d_w ** 2 / 2 - (
#                 model.I_z - model.I_x - model.m_b * model.l ** 2) * np.sin(theta) ** 2
#         B_3 = model.d_w / (2 * model.r_w)
#         C_13 = (model.I_y + model.m_b * model.l ** 2) * model.m_b * model.l + model.m_b * model.l * (
#                 model.I_z - model.I_x - model.m_b * model.l ** 2) * np.cos(theta) ** 2
#         C_23 = (model.m_b ** 2 * model.l ** 2 + (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * (
#                 model.I_z - model.I_x - model.m_b * model.l ** 2)) * np.cos(theta)
#
#         state_dot = np.zeros(self.n)
#         state_dot[0] = v
#         state_dot[1] = (np.sin(theta) / V_1) * (-C_11 * g + C_12 * theta_dot ** 2) - (D_11 / V_1) * v + (
#                 D_12 / V_1) * theta_dot + (B_1 / V_1) * u[0] - model.tau_x * v
#         state_dot[2] = theta_dot
#         state_dot[3] = (np.sin(theta) / V_1) * (C_21 * g - C_22 * theta_dot ** 2) + (D_21 / V_1) * v - (
#                 D_22 / V_1) * theta_dot - (B_2 / V_1) * u[0] - model.tau_theta * theta_dot
#         state = state + state_dot * self.Ts
#         return state
#
#     def _output_function(self, state):
#         return state['theta']
#
#     def _output(self, state: sp.State):
#         pass
#
#     def init(self):
#         pass
#
#
# class BILBO_3D_Linear(core.dynamics.LinearDynamics):
#     """
#     Linear dynamics for BILBO in 3D.
#     Computes a discrete-time state-feedback controller.
#     """
#     state_space = BILBO_3D_StateSpace_6D()
#     input_space = BILBO_3D_InputSpace()
#     output_space = BILBO_3D_StateSpace_6D()
#
#     def __init__(self, model: BilboModel, Ts, poles=None, ev=None):
#         self.model = model
#         self.Ts = Ts
#         A_cont, B_cont, C_cont, D_cont = self._linear_model()
#         self.sys_cont = control.StateSpace(A_cont, B_cont, C_cont, D_cont, remove_useless_states=False)
#
#         sys_disc = control.c2d(self.sys_cont, Ts)
#         self.A = sys_disc.A
#         self.B = sys_disc.B
#         self.C = sys_disc.C
#         self.D = sys_disc.D
#
#         super().__init__(Ts=Ts)
#         if poles is not None and ev is None:
#             self.K = self.set_poles(poles)
#         elif poles is not None and ev is not None:
#             self.K = self.set_eigenstructure(poles, ev)
#         else:
#             self.K = np.zeros((self.p, self.n))
#
#     def _linear_model(self):
#         g = 9.81
#         model = self.model
#         C_21 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * model.m_b * model.l
#         V_1 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * (
#                 model.I_y + model.m_b * model.l ** 2) - model.m_b ** 2 * model.l ** 2
#         D_22 = (
#                        model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha + model.m_b * model.l * 2 * model.c_alpha / model.r_w
#         D_21 = (
#                        model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha / model.r_w + model.m_b * model.l * 2 * model.c_alpha / model.r_w ** 2
#         C_11 = model.m_b ** 2 * model.l ** 2
#         D_12 = (
#                        model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w - model.m_b * model.l * 2 * model.c_alpha
#         D_11 = (
#                        model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w ** 2 - model.m_b * model.l * 2 * model.c_alpha / model.r_w
#         D_33 = model.d_w ** 2 / (2 * model.r_w ** 2) * model.c_alpha
#         V_2 = model.I_z + 2 * model.I_w + (model.m_w + model.I_w / model.r_w ** 2) * model.d_w ** 2 / 2
#         A = np.array([
#             [0, 1, 0, 0, 0, 0],
#             [0, -D_11 / V_1, -C_11 * g / V_1, D_12 / V_1, 0, 0],
#             [0, 0, 0, 1, 0, 0],
#             [0, D_21 / V_1, C_21 * g / V_1, -D_22 / V_1, 0, 0],
#             [0, 0, 0, 0, 0, 1],
#             [0, 0, 0, 0, 0, -D_33 / V_2]
#         ])
#         B_1 = (model.I_y + model.m_b * model.l ** 2) / model.r_w + model.m_b * model.l
#         B_2 = model.m_b * model.l / model.r_w + model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2
#         B_3 = model.d_w / (2 * model.r_w)
#         B = np.array([
#             [0, 0],
#             [B_1 / V_1, B_1 / V_1],
#             [0, 0],
#             [-B_2 / V_1, -B_2 / V_1],
#             [0, 0],
#             [-B_3 / V_2, B_3 / V_2]
#         ])
#         C = np.array([[0, 0, 1, 0, 0, 0]])
#         D = [0, 0]
#         return A, B, C, D
#
#     def set_poles(self, poles):
#         poles = np.asarray(poles)
#         self.K = np.asarray(control.place(self.A, self.B, np.exp(poles * self.Ts)))
#         A_hat = self.A - self.B @ self.K
#         self.A = A_hat
#         self.sys = control.StateSpace(self.A, self.B, self.C, self.D, self.Ts, remove_useless_states=False)
#         if hasattr(self, 'sys_cont') and self.sys_cont is not None:
#             K = np.asarray(control.place(self.sys_cont.A, self.sys_cont.B, poles))
#             self.sys_cont = control.StateSpace((self.sys_cont.A - self.sys_cont.B @ K), self.sys_cont.B,
#                                                self.sys_cont.C, self.sys_cont.D, remove_useless_states=False)
#         return self.K
#
#     def set_eigenstructure(self, poles, ev, set=True):
#         poles = np.asarray(poles)
#         K = lib_control.eigenstructure_assignment(self.A, self.B, np.exp(poles * self.Ts), ev)
#         if set:
#             self.K = K
#             A_hat = self.A - self.B @ self.K
#             self.A = A_hat
#             self.sys = control.StateSpace(self.A, self.B, self.C, self.D, self.Ts, remove_useless_states=False)
#         return K
#
#
# class BILBO_3D_Linear_XY(core.dynamics.LinearDynamics):
#     """
#     Linear dynamics for BILBO in 3D with a 7D state:
#       [x, y, v, theta, theta_dot, psi, psi_dot]
#
#     The first two states are the Cartesian coordinates obtained from the kinematics
#     x_dot = v*cos(psi) and y_dot = v*sin(psi). These equations are linearized about an
#     operating point (v0, psi0) – by default psi0 = 0 and v0 = 0.
#
#     The remaining states (v, theta, theta_dot, psi, psi_dot) follow the same linearized
#     dynamics as in the original 3D model (which used s instead of x,y).
#
#     A discrete-time state-feedback controller is computed from the continuous linear model.
#     """
#     state_space = BILBO_3D_StateSpace_7D()
#     input_space = BILBO_3D_InputSpace()
#     output_space = BILBO_3D_StateSpace_7D()
#
#     def __init__(self, model: BilboModel, Ts, poles=None, ev=None, v0=0, psi0=0):
#         self.model = model
#         self.Ts = Ts
#         self.v0 = v0  # Operating point forward velocity (for kinematics linearization)
#         self.psi0 = psi0  # Operating point heading
#         A_cont, B_cont, C_cont, D_cont = self._linear_model()
#         self.sys_cont = control.StateSpace(A_cont, B_cont, C_cont, D_cont, remove_useless_states=False)
#         self.sys_disc = control.c2d(self.sys_cont, Ts)
#         self.A = np.asarray(self.sys_disc.A)
#         self.B = np.asarray(self.sys_disc.B)
#         self.C = np.asarray(self.sys_disc.C)
#         self.D = np.asarray(self.sys_disc.D)
#         super().__init__(Ts=Ts)
#         # Design state-feedback gains if poles are provided.
#         if poles is not None and ev is None:
#             self.K = self.set_poles(poles)
#         elif poles is not None and ev is not None:
#             self.K = self.set_eigenstructure(poles, ev)
#         else:
#             self.K = np.zeros((self.p, self.n))
#
#     def _linear_model(self):
#         g = 9.81
#         model = self.model
#         # Compute common terms from the original 3D linear model.
#         C_21 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * model.m_b * model.l
#         V_1 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * (
#                 model.I_y + model.m_b * model.l ** 2) - model.m_b ** 2 * model.l ** 2
#         D_22 = ((
#                         model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha + model.m_b * model.l * 2 * model.c_alpha / model.r_w)
#         D_21 = ((
#                         model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha / model.r_w + model.m_b * model.l * 2 * model.c_alpha / model.r_w ** 2)
#         C_11 = model.m_b ** 2 * model.l ** 2
#         D_12 = ((
#                         model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w - model.m_b * model.l * 2 * model.c_alpha)
#         D_11 = ((
#                         model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w ** 2 - model.m_b * model.l * 2 * model.c_alpha / model.r_w)
#         D_33 = model.d_w ** 2 / (2 * model.r_w ** 2) * model.c_alpha
#         V_2 = model.I_z + 2 * model.I_w + (model.m_w + model.I_w / model.r_w ** 2) * model.d_w ** 2 / 2
#
#         # Linearize the kinematic equations about (v0, psi0).
#         cos_psi0 = np.cos(self.psi0)
#         sin_psi0 = np.sin(self.psi0)
#
#         # Construct A matrix with state ordering: [x, y, v, theta, theta_dot, psi, psi_dot]
#         A = np.zeros((7, 7))
#         # Kinematics for x and y:
#         # x_dot = v*cos(psi) ≈ cos(psi0)*delta_v - v0*sin(psi0)*delta_psi
#         A[0, 2] = cos_psi0
#         A[0, 5] = -self.v0 * sin_psi0
#         # y_dot = v*sin(psi) ≈ sin(psi0)*delta_v + v0*cos(psi0)*delta_psi
#         A[1, 2] = sin_psi0
#         A[1, 5] = self.v0 * cos_psi0
#
#         # The remaining dynamics are taken from the original model.
#         # v dynamics (originally row 1 for state 'v'):
#         A[2, 2] = -D_11 / V_1
#         A[2, 3] = -C_11 * g / V_1
#         A[2, 4] = D_12 / V_1
#         # Theta kinematics: theta_dot = dot(theta)
#         A[3, 4] = 1.0
#         # Theta_dot dynamics (originally row 3):
#         A[4, 2] = D_21 / V_1
#         A[4, 3] = C_21 * g / V_1
#         A[4, 4] = -D_22 / V_1
#         # Psi kinematics: psi_dot = dot(psi)
#         A[5, 6] = 1.0
#         # Psi_dot dynamics (originally row 5):
#         A[6, 6] = -D_33 / V_2
#
#         # Construct B matrix with ordering: [x, y, v, theta, theta_dot, psi, psi_dot]
#         B = np.zeros((7, 2))
#         # Only the internal dynamics (v, theta_dot, psi_dot) are actuated.
#         # v dynamics (originally row 1):
#         B[2, :] = [((model.I_y + model.m_b * model.l ** 2) / model.r_w + model.m_b * model.l) / V_1,
#                    ((model.I_y + model.m_b * model.l ** 2) / model.r_w + model.m_b * model.l) / V_1]
#         # Theta_dot dynamics (originally row 3):
#         B[4, :] = [
#             - (model.m_b * model.l / model.r_w + model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) / V_1,
#             - (model.m_b * model.l / model.r_w + model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) / V_1]
#         # Psi_dot dynamics (originally row 5):
#         B[6, :] = [- model.d_w / (2 * model.r_w) / V_2,
#                    model.d_w / (2 * model.r_w) / V_2]
#
#         # Define the output matrix. Here we choose to output theta (state index 3), for example.
#         C = np.array([[0, 0, 0, 1, 0, 0, 0]])
#         D = np.array([0, 0])
#
#         return A, B, C, D
#
#     def set_poles(self, poles):
#         poles = np.asarray(poles)
#         # Compute the discrete-time desired poles (using the exponential mapping).
#         self.K = np.asarray(control.place(self.A, self.B, np.exp(poles * self.Ts)))
#         A_hat = self.A - self.B @ self.K
#         self.A = A_hat
#         self.sys = control.StateSpace(self.A, self.B, self.C, self.D, self.Ts, remove_useless_states=False)
#         if hasattr(self, 'sys_cont') and self.sys_cont is not None:
#             K = np.asarray(control.place(self.sys_cont.A, self.sys_cont.B, poles))
#             self.sys_cont = control.StateSpace((self.sys_cont.A - self.sys_cont.B @ K),
#                                                self.sys_cont.B,
#                                                self.sys_cont.C,
#                                                self.sys_cont.D,
#                                                remove_useless_states=False)
#         return self.K
#
#     def set_eigenstructure(self, poles, ev, set=True):
#         poles = np.asarray(poles)
#         K = lib_control.eigenstructure_assignment(self.A, self.B, np.exp(poles * self.Ts), ev)
#         if set:
#             self.K = K
#             A_hat = self.A - self.B @ self.K
#             self.A = A_hat
#             self.sys = control.StateSpace(self.A, self.B, self.C, self.D, self.Ts, remove_useless_states=False)
#         return K
#
#
# class BILBO_Dynamics_3D(core.dynamics.Dynamics):
#     """
#     3D dynamics for BILBO.
#     This model uses a 7-dimensional state and accepts 2 inputs.
#     """
#     state_space = BILBO_3D_StateSpace_7D
#     input_space = BILBO_3D_InputSpace
#     output_space = BILBO_3D_StateSpace_7D
#
#     def __init__(self, model: BilboModel, Ts, *args,
#                  **kwargs):
#         super().__init__(Ts=Ts, *args, **kwargs)
#         self.model = model
#         # Limit the pitch (theta) to the maximum allowed value from the model.
#         # self.state_space['theta'].limits = [-self.model.max_pitch, self.model.max_pitch]
#         self.q = 1
#         self.p = 2
#         self.n = 7
#
#     def update(self, input=None):
#         if input is not None:
#             self.input = input
#         self.state = self._dynamics(self.state, self.input)
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def _dynamics(self, state, input):
#         g = 9.81
#         x = state[0].value
#         y = state[1].value
#         v = state[2].value
#         theta = state[3].value
#         theta_dot = state[4].value
#         psi = state[5].value
#         psi_dot = state[6].value
#         u = [input[0].value, input[1].value]
#         model = self.model
#         C_12 = (model.I_y + model.m_b * model.l ** 2) * model.m_b * model.l
#         C_22 = model.m_b ** 2 * model.l ** 2 * np.cos(theta)
#         C_21 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * model.m_b * model.l
#         V_1 = (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * (
#                 model.I_y + model.m_b * model.l ** 2) - model.m_b ** 2 * model.l ** 2 * np.cos(theta) ** 2
#         D_22 = (
#                        model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha + model.m_b * model.l * np.cos(
#             theta) * 2 * model.c_alpha / model.r_w
#         D_21 = (
#                        model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * 2 * model.c_alpha / model.r_w + model.m_b * model.l * np.cos(
#             theta) * 2 * model.c_alpha / model.r_w ** 2
#         C_11 = model.m_b ** 2 * model.l ** 2 * np.cos(theta)
#         D_12 = (model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w - model.m_b * model.l * np.cos(
#             theta) * 2 * model.c_alpha
#         D_11 = (
#                        model.I_y + model.m_b * model.l ** 2) * 2 * model.c_alpha / model.r_w ** 2 - 2 * model.m_b * model.l * np.cos(
#             theta) * model.c_alpha / model.r_w
#         B_2 = model.m_b * model.l / model.r_w * np.cos(
#             theta) + model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2
#         B_1 = (model.I_y + model.m_b * model.l ** 2) / model.r_w + model.m_b * model.l * np.cos(theta)
#         C_31 = 2 * (model.I_z - model.I_x - model.m_b * model.l ** 2) * np.cos(theta)
#         C_32 = model.m_b * model.l
#         D_33 = model.d_w ** 2 / (2 * model.r_w ** 2) * model.c_alpha
#         V_2 = model.I_z + 2 * model.I_w + (model.m_w + model.I_w / model.r_w ** 2) * model.d_w ** 2 / 2 - (
#                 model.I_z - model.I_x - model.m_b * model.l ** 2) * np.sin(theta) ** 2
#         B_3 = model.d_w / (2 * model.r_w)
#         C_13 = (model.I_y + model.m_b * model.l ** 2) * model.m_b * model.l + model.m_b * model.l * (
#                 model.I_z - model.I_x - model.m_b * model.l ** 2) * np.cos(theta) ** 2
#         C_23 = (model.m_b ** 2 * model.l ** 2 + (model.m_b + 2 * model.m_w + 2 * model.I_w / model.r_w ** 2) * (
#                 model.I_z - model.I_x - model.m_b * model.l ** 2)) * np.cos(theta)
#
#         state_dot = np.zeros(self.n)
#         state_dot[0] = v * np.cos(psi)
#         state_dot[1] = v * np.sin(psi)
#         state_dot[2] = (np.sin(theta) / V_1) * (-C_11 * g + C_12 * theta_dot ** 2 + C_13 * psi_dot ** 2) - (
#                 D_11 / V_1) * v + (D_12 / V_1) * theta_dot + (B_1 / V_1) * (u[0] + u[1]) - model.tau_x * v
#         state_dot[3] = theta_dot
#         state_dot[4] = (np.sin(theta) / V_1) * (C_21 * g - C_22 * theta_dot ** 2 - C_23 * psi_dot ** 2) + (
#                 D_21 / V_1) * v - (D_22 / V_1) * theta_dot - (B_2 / V_1) * (
#                                u[0] + u[1]) - model.tau_theta * theta_dot
#         state_dot[5] = psi_dot
#         state_dot[6] = (np.sin(theta) / V_2) * (C_31 * theta_dot * psi_dot - C_32 * psi_dot * v) - (
#                 D_33 / V_2) * psi_dot - (B_3 / V_2) * (u[0] - u[1])
#         state = state + state_dot * self.Ts
#         return state
#
#     def _output(self, state):
#         return state['theta']
#
#     def init(self):
#         ...
#
#
# # -----------------------------------------------------------------------------
# # BILBO AGENTS
# # -----------------------------------------------------------------------------
# class BILBO_Agent(core.agents.Agent):
#     """
#     Base agent for BILBO.
#     """
#     object_type: str = 'bilbo_agent'
#     space = Space3D_BILBO()
#
#     def __init__(self, agent_id, *args, **kwargs):
#         # Set unique id (do not use "name")
#         self.id = f"BILBO_{agent_id}"
#         super().__init__(agent_id=agent_id, *args, **kwargs)
#         self.physics: BILBO_PhysicalObject = BILBO_PhysicalObject()
#
#     def _getParameters(self):
#         params = super()._getParameters()
#         params['physics'] = {}
#         params['size'] = {
#             'x': self.physics.depth,
#             'y': self.physics.width,
#             'z': self.physics.height
#         }
#         params['physics']['size'] = [self.physics.depth, self.physics.width, self.physics.height]
#         params['physics']['wheel_diameter'] = self.physics.wheel_diameter
#         params['physics']['l_w'] = self.physics.l_w
#         return params
#
#     def _getSample(self):
#         sample = super()._getSample()
#         sample['collision_box_pos'] = {
#             'x': self.physics.bounding_objects['body'].position[0],
#             'y': self.physics.bounding_objects['body'].position[1],
#             'z': self.physics.bounding_objects['body'].position[2]
#         }
#         return sample
#
#     def _init(self, *args, **kwargs):
#         self._updatePhysics()
#
#
# # ======================================================================================================================
# # BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES = [0, -20, -3 + 3j, -3 - 3j, 0, -15]
#
#
# class BILBO_Agent_Control_Mode(enum.IntEnum):
#     OFF = 0,
#     DIRECT = 1,
#     BALANCING = 2,
#     VELOCITY = 3,
#
#
# class BILBO_DynamicAgent(BILBO_Agent, core.agents.DynamicAgent):
#     """
#     Dynamic agent for BILBO that incorporates control and feedback.
#     """
#     object_type: str = 'bilbo_agent'
#     space = Space3D_BILBO()
#     # space = BILBO_3D_StateSpace_6D()
#     dynamics: BILBO_Dynamics_3D
#     linear_dynamics: BILBO_3D_Linear
#
#     velocity_input_space = BILBO_3D_VelocityInputSpace()
#     input_space = BILBO_3D_InputSpace()
#
#     control_mode: BILBO_Agent_Control_Mode
#
#     Ts = DEFAULT_SAMPLE_TIME
#
#     def __init__(self, agent_id,
#                  speed_control: bool = False,
#                  poles=None,
#                  eigenvectors=None,
#                  K=None,
#                  model: BilboModel = DEFAULT_BILBO_MODEL,
#                  enable_state_constraints: bool = True,
#                  *args,
#                  **kwargs):
#
#         # Instantiate dynamics with provided sample time and model.
#         if poles is None:
#             poles = BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES
#
#         if eigenvectors is None:
#             eigenvectors = BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS
#
#         self.model = model
#         self._enable_state_constraints = enable_state_constraints
#
#         self.dynamics = BILBO_Dynamics_3D(Ts=self.Ts, model=model)
#
#         super().__init__(agent_id=agent_id, *args, **kwargs)
#
#         # self.controller_v = lib_control.PID_ctrl(Ts=self.Ts, P=-1.534 / 2, I=-2.81 / 2, D=-0.07264 / 2, max_rate=75)
#         # self.controller_psidot = lib_control.PID_ctrl(Ts=self.Ts, P=-0.3516, I=-1.288, D=-0.0002751)
#
#         self.mode = BILBO_Agent_Control_Mode.BALANCING
#
#         self.poles = poles
#         self.linear_dynamics = BILBO_3D_Linear(self.model, self.Ts, poles, eigenvectors)
#
#         self.dynamics_2d = BILBO_Dynamics_2D()
#         self.linear_dynamics_2d = ...
#
#         # Combine a zero column with the computed gain matrix.
#         self.state_ctrl_K = np.hstack((np.zeros((2, 1)), self.linear_dynamics.K))
#
#         if K is not None:
#             self.state_ctrl_K = K
#
#         self.input = self.input_space.getState()
#         # self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.LOGIC].addAction(self._controller)
#         self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.DYNAMICS].addAction(self._calculateStateConstraints)
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def _controller(self):
#
#         if self.mode == BILBO_Agent_Control_Mode.OFF:
#             self.input = [0, 0]
#             self.dynamics.input = [0, 0]
#         elif self.mode == BILBO_Agent_Control_Mode.BALANCING:
#             input_dynamics = self.input
#             input_dynamics = input_dynamics - self.state_ctrl_K @ self.state
#             self.dynamics.input = input_dynamics
#
#     # ------------------------------------------------------------------------------------------------------------------
#     @property
#     def input(self):
#         return self._input
#
#     # ------------------------------------------------------------------------------------------------------------------
#     @input.setter
#     def input(self, value: list | np.ndarray | core.spaces.State):
#         if value is not None and value[0] == 0:
#             pass
#         self._input = self.input_space.map(value)
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def reset(self):
#         self.state = self.dynamics.state_space.getState()
#         self.input = self.input_space.getState()
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def _calculateStateConstraints(self):
#         if not self._enable_state_constraints:
#             return
#
#         import math
#
#         # --- dt & params ---
#         dt = float(getattr(self.dynamics, "Ts", getattr(self, "Ts", DEFAULT_SAMPLE_TIME)))
#         max_pitch = float(self.model.max_pitch)
#         tol_enter = 1e-4
#         tol_exit = 2e-4
#
#         # contact tunables (feel free to expose in BilboModel)
#         e_n = float(getattr(self.model, "restitution_n", 0.0))  # normal restitution
#         k_t = float(getattr(self.model, "tangent_decay", 12.0))  # 1/s, v decay
#         k_r = float(getattr(self.model, "yaw_decay", 10.0))  # 1/s, psi_dot decay
#
#         # use slightly larger stick thresholds to kill drift
#         v_stick = float(getattr(self.model, "v_stick", 5e-3))  # m/s
#         w_stick = float(getattr(self.model, "w_stick", 5e-3))  # rad/s
#
#         # --- initialize persistent stuff ---
#         if not hasattr(self, "_ground_contact"):
#             self._ground_contact = False
#         if not hasattr(self, "_prev_pose"):
#             self._prev_pose = {
#                 "x": float(self.dynamics.state['x'].value),
#                 "y": float(self.dynamics.state['y'].value),
#                 "psi": float(self.dynamics.state['psi'].value),
#             }
#
#         # --- read state ---
#         x = float(self.dynamics.state['x'].value)
#         y = float(self.dynamics.state['y'].value)
#         v = float(self.dynamics.state['v'].value)
#         theta = float(self.dynamics.state['theta'].value)
#         theta_dot = float(self.dynamics.state['theta_dot'].value)
#         psi = float(self.dynamics.state['psi'].value)
#         psi_dot = float(self.dynamics.state['psi_dot'].value)
#
#         # contact detection (hysteresis)
#         side = 1.0 if theta >= 0.0 else -1.0
#         depth = abs(theta) - max_pitch
#         approaching = (theta_dot * side) > 0.0
#
#         if depth > 0.0 or (abs(abs(theta) - max_pitch) <= tol_enter and approaching):
#             self._ground_contact = True
#         elif abs(abs(theta) - max_pitch) > tol_exit and not approaching:
#             self._ground_contact = False
#
#         sticking = False
#
#         if self._ground_contact:
#             # project onto contact manifold
#             theta = side * max_pitch
#
#             # normal velocity treatment
#             if approaching:
#                 theta_dot = -e_n * theta_dot
#             if abs(theta_dot) < w_stick:
#                 theta_dot = 0.0
#
#             # tangential exponential decay (dt-aware)
#             decay_t = math.exp(-k_t * dt)
#             decay_r = math.exp(-k_r * dt)
#             v *= decay_t
#             psi_dot *= decay_r
#
#             # stick if small
#             if abs(v) < v_stick:
#                 v = 0.0
#             if abs(psi_dot) < w_stick:
#                 psi_dot = 0.0
#
#             sticking = (v == 0.0 and psi_dot == 0.0)
#
#             # *** key anti-drift step: rollback pose when sticking ***
#             if sticking:
#                 x = self._prev_pose["x"]
#                 y = self._prev_pose["y"]
#                 psi = self._prev_pose["psi"]
#
#         else:
#             # if we notice penetration outside contact, resolve once
#             if depth > 0.0:
#                 theta = side * max_pitch
#                 if approaching:
#                     theta_dot = -e_n * theta_dot
#
#         # write back
#         self.dynamics.state['x'] = x
#         self.dynamics.state['y'] = y
#         self.dynamics.state['v'] = v
#         self.dynamics.state['theta'] = theta
#         self.dynamics.state['theta_dot'] = theta_dot
#         self.dynamics.state['psi'] = psi
#         self.dynamics.state['psi_dot'] = psi_dot
#
#         # update snapshot for next step (must be after any rollback)
#         self._prev_pose = {"x": x, "y": y, "psi": psi}
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def _getParameters(self):
#         params = super()._getParameters()
#         params['physics'] = {}
#         params['size'] = {
#             'x': self.physics.depth,
#             'y': self.physics.width,
#             'z': self.physics.height
#         }
#         params['physics']['size'] = [self.physics.depth, self.physics.width, self.physics.height]
#         params['physics']['wheel_diameter'] = self.physics.wheel_diameter
#         params['physics']['l_w'] = self.physics.l_w
#         return params
#
#     def _getSample(self):
#         sample = super()._getSample()
#         return sample
#
#     def _init(self, *args, **kwargs):
#         self._updatePhysics()
#
#     def _action_control(self):
#         # Placeholder for additional control actions if needed.
#         pass
#
#     def action_output(self, *args, **kwargs):
#         self.output = self.state
#
#     @staticmethod
#     def get3DInputFrom2D(input: np.ndarray):
#         # return hstack([input / 2, input / 2])
#         return np.column_stack((input / 2, input / 2))
#
#
# if __name__ == '__main__':
#     model = DEFAULT_BILBO_MODEL
#
#     x = BILBO_Dynamics_2D_Linear(model=model, Ts=0.02, poles=[0, -20, -2 + 2j, -2 - 2j])
#     print(x.K_disc)
