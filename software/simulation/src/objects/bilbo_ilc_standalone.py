import dataclasses

import numpy as np
from matplotlib import pyplot as plt
from numpy import nan
import control
import scipy


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
    I_y: float
    I_x: float
    I_z: float
    c_alpha: float
    r_w: float
    tau_theta: float
    tau_x: float
    max_pitch: float


DEFAULT_BILBO_MODEL = BilboModel(
    m_b=2.5,
    m_w=0.636,
    l=0.026,
    d_w=0.28,
    I_w=5.1762e-4,
    I_y=0.01648,
    I_x=0.02,
    I_z=0.03,
    c_alpha=4.6302e-4,
    r_w=0.055,
    tau_theta=1,
    tau_x=1,
    max_pitch=np.deg2rad(105)
)

bilbo_eigenstructure_assignment_poles = [0, -20, -3 + 3j, -3 - 3j, 0, -15]

bilbo_eigenstructure_assignment_eigenvectors = np.array([[1, nan, nan, nan, 0, nan],
                                                         [nan, 1, nan, nan, nan, nan],
                                                         [nan, nan, 1, 1, nan, 0],
                                                         [nan, nan, nan, nan, nan, nan],
                                                         [0, nan, nan, nan, 1, 1],
                                                         [nan, 0, 0, 0, nan, nan]])

bilbo_example_reference = np.asarray([0, 0.000197760222250443, 2.11803678398722e-05, -0.00192431976122926,
                                      -0.00615332730270171, -0.0109469705842174, -0.0109726750284568,
                                      0.00314109970339850, 0.0424997242039622, 0.112410684401934, 0.206956128623623,
                                      0.314388776117438, 0.424624384030855, 0.531504092587520, 0.632344339907318,
                                      0.726580774482237, 0.814500854214386, 0.896435127229825, 0.972408345000750,
                                      1.04209766198346, 1.10493026693230, 1.16020644070794, 1.20720625476184,
                                      1.24529862610457, 1.27410193519773, 1.29373142884650, 1.30509563459453,
                                      1.31006134120138, 1.31110201565285, 1.31047295027832, 1.30963323863495,
                                      1.30922177157536, 1.30930631662257, 1.30965982770113, 1.30996481191886,
                                      1.30994972434867, 1.30949786773374, 1.30875254893503, 1.30818871082097,
                                      1.30855196124135, 1.31051378028126, 1.31390920626002, 1.31658347179794,
                                      1.31325479714354, 1.29544137534898, 1.25367888373710, 1.18092399658192,
                                      1.07430141167592, 0.934822844842898, 0.766570547670360, 0.576190859740028,
                                      0.372759963677128, 0.167424548076854, -0.0283162793280289, -0.207136794339771,
                                      -0.368318377418767, -0.513567846522248, -0.642925092434494, -0.754407918301252,
                                      -0.844997331803202, -0.912193494933843, -0.955634172298121, -0.978235135241612,
                                      -0.985958478482436, -0.985709523100663, -0.982841873248806, -0.980233404456636,
                                      -0.978812523403062, -0.978465073275781, -0.978773146960503,
                                      -0.979413455756401, - 0.980247798771826, -0.981219159659383, -0.982180374666072,
                                      -0.982769568783324, -0.982426074885620, -0.980609358807766, -0.977224675287443,
                                      -0.973154087874496, -0.970636351537536, -0.973065802731135, -0.983677050076961,
                                      -1.00270542555312, -1.02317436868087, -1.02666525392914, -0.982336312751358,
                                      -0.854772438038150, -0.627994145762945, -0.352177508147913, -0.125419966807256,
                                      0.00210811409895107, 0.0463974593171859, 0.0428788688598347,
                                      0.0224111802076914, 0.00342562788370501 - 0.00710124071239199,
                                      -0.00942546473025664, -0.00682637673985390, -0.00275955516620977,
                                      0.000481842027831330, 0.00200718542849226, 0.00199239375341818,
                                      0.00117230609516377, 0.000378721640301647, 0.000183951257060003,
                                      0.00062972961798011, 0.00103310868987361, -4.31887979877787e-05])


def qlearning(P: np.ndarray, Qw, Rw, Sw):
    if isinstance(Qw, (int, float)):
        Qw = Qw * np.eye(P.shape[0])
    if isinstance(Rw, (int, float)):
        Rw = Rw * np.eye(P.shape[0])
    if isinstance(Sw, (int, float)):
        Sw = Sw * np.eye(P.shape[0])

    Q = np.linalg.inv(P.T @ Qw @ P + Rw + Sw) @ (P.T @ Qw @ P + Sw)
    L = np.linalg.inv(P.T @ Qw @ P + Sw) @ P.T @ Qw
    return Q, L


def eigenstructure_assignment(A, B, poles, eigenvectors):
    N = A.shape[0]
    M = B.shape[1]

    reduced_ev = [None] * N
    D = [None] * N

    for i in range(0, N):
        reduced_ev[i] = eigenvectors[~np.isnan(eigenvectors[:, i]), i]
        reduced_ev[i] = np.atleast_2d(reduced_ev[i]).T
        D_i = np.zeros((M, N))
        V_temp = ~np.isnan(eigenvectors[:, i])
        indexes = np.argwhere(V_temp == 1)

        for j in range(0, M):
            D_i[j, indexes[j]] = 1
        D[i] = D_i

    b = [None] * N
    x = [None] * N
    r = [None] * N

    for i in range(0, N):
        mat_temp = np.vstack((np.hstack((A - poles[i] * np.eye(N), B)), np.hstack((D[i], np.zeros((M, M))))))
        vec_temp = np.vstack((np.zeros((N, 1)), reduced_ev[i]))
        b[i] = np.linalg.inv(mat_temp) @ vec_temp
        x[i] = b[i][0:N]
        r[i] = -b[i][N:N + M]

    X = np.zeros((N, N), dtype=complex)
    R = np.zeros((M, N), dtype=complex)
    for i in range(0, N):
        X[:, i] = x[i][:, 0]
        R[:, i] = r[i][:, 0]

    K = np.real(R @ np.linalg.inv(X))
    if np.isnan(np.sum(K)):
        raise Exception("Eigenstructure assignment not possible!")
    return K


def dlqr(A, B, Q, R):
    # first, try to solve the ricatti equation
    X = np.matrix(scipy.linalg.solve_discrete_are(A, B, Q, R))

    # compute the LQR gain
    K = np.matrix(scipy.linalg.inv(B.T * X * B + R) * (B.T * X * A))

    eigVals, eigVecs = scipy.linalg.eig(A - B * K)

    K = np.asarray(K)
    return K, X, eigVals


def relative_degree(sys):
    # warnings.warn("Relative degree not implemented yet!")
    return 1


def calc_transition_matrix(sys, N):
    if sys.dt is None:
        raise Exception("System has to be discrete time!")

    m = relative_degree(sys)
    P = np.zeros((N, N))

    diag, P2 = np.linalg.eig(sys.A)

    for i in range(0, N):
        for j in range(0, N):
            markov_m = m + i - j
            if markov_m < m:
                P[i, j] = 0
            else:
                P[i, j] = (sys.C @ np.linalg.matrix_power(sys.A, (markov_m - 1)) @ sys.B).item()

    return P


class BILBO_Dynamics_2D_Linear:
    """
    Linearized dynamics for the BILBO robot (2D model).
    Converts a continuous-time model to discrete time and computes state-feedback gains.
    """

    def __init__(self, model: BilboModel, Ts, K_cont):
        self.Ts = Ts
        self.model = model
        self.K = np.asarray(K_cont).reshape(1, 4)

        self.n = 4  # number of states
        self.p = 1
        self.q = 1
        # Compute continuous-time model matrices.
        self.A, self.B, self.C, self.D = self.linear_model()
        self.sys_cont = control.StateSpace((self.A - self.B @ self.K), self.B, self.C, self.D,
                                           remove_useless_states=False)

        self.sys_disc = control.c2d(self.sys_cont, self.Ts)
        self.A_d = np.asarray(self.sys_disc.A)
        self.B_d = np.asarray(self.sys_disc.B)
        self.C_d = np.asarray(self.sys_disc.C)
        self.D_d = np.asarray(self.sys_disc.D)

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


# ----------------------------------------------------------------------------------------------------------------------
class BILBO_Dynamics_3D_Linear:
    """
    Linear dynamics for BILBO in 3D.
    Computes a discrete-time state-feedback controller.
    """

    p: int = 2
    n: int = 6

    def __init__(self, model, Ts, poles=None, ev=None):
        self.model = model
        self.Ts = Ts
        A_cont, B_cont, C_cont, D_cont = self._linear_model()
        self.sys_cont = control.StateSpace(A_cont, B_cont, C_cont, D_cont, remove_useless_states=False)
        self.sys_disc = control.c2d(self.sys_cont, Ts)
        self.A = self.sys_disc.A
        self.B = self.sys_disc.B
        self.C = self.sys_disc.C
        self.D = self.sys_disc.D
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
        V_2 = model.I_z + 2 * model.I_w + (model.m_w + model.I_w / model.r_w ** 2) * model.d_w ** 2 / 2
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

    def step(self, state, input):
        x_dot = self.A @ state + self.B @ input
        state = state + self.Ts * x_dot
        return state

    def set_eigenstructure(self, poles, ev):
        poles = np.asarray(poles)
        K = eigenstructure_assignment(self.A, self.B, np.exp(poles * self.Ts), ev)
        return K


class BILBO_Dynamics_3D_Nonlinear:
    """
    3D dynamics for BILBO.
    This model uses a 7-dimensional state and accepts 2 inputs.
    """

    def __init__(self, model, Ts, *args, **kwargs):
        self.model = model
        self.q = 1
        self.p = 2
        self.n = 7
        self.Ts = Ts

    def step(self, state, input):
        return self._dynamics(state, input)

    def _dynamics(self, state, input):
        g = 9.81
        x = state[0]
        y = state[1]
        v = state[2]
        theta = state[3]
        theta_dot = state[4]
        psi = state[5]
        psi_dot = state[6]
        u = [input[0], input[1]]
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
        V_2 = model.I_z + 2 * model.I_w + (model.m_w + model.I_w / model.r_w ** 2) * model.d_w ** 2 / 2 - (
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
        state_dot[4] = (np.sin(theta) / V_1) * (C_21 * g - C_22 * theta_dot ** 2 - C_23 * psi_dot ** 2) + (
                D_21 / V_1) * v - (D_22 / V_1) * theta_dot - (B_2 / V_1) * (
                               u[0] + u[1]) - model.tau_theta * theta_dot
        state_dot[5] = psi_dot
        state_dot[6] = (np.sin(theta) / V_2) * (C_31 * theta_dot * psi_dot - C_32 * psi_dot * v) - (
                D_33 / V_2) * psi_dot - (B_3 / V_2) * (u[0] - u[1])
        state = state + state_dot * self.Ts
        return state


class BILBO:
    linear_dynamics: BILBO_Dynamics_3D_Linear
    linear_dynamics_2d: BILBO_Dynamics_2D_Linear
    nonlinear_dynamics: BILBO_Dynamics_3D_Nonlinear
    model: BilboModel

    state: np.ndarray
    input: np.ndarray

    def __init__(self, model=DEFAULT_BILBO_MODEL, mode: str = 'nonlinear', Ts=0.01, poles=None, eigenvectors=None):
        self.model = model
        self.Ts = Ts

        assert mode in ['linear', 'nonlinear']

        self.mode = mode

        if poles is None:
            poles = bilbo_eigenstructure_assignment_poles
        if eigenvectors is None:
            eigenvectors = bilbo_eigenstructure_assignment_eigenvectors

        self.poles = poles
        self.eigenvectors = eigenvectors

        self.linear_dynamics = BILBO_Dynamics_3D_Linear(model, Ts=self.Ts, poles=self.poles, ev=self.eigenvectors)
        self.nonlinear_dynamics = BILBO_Dynamics_3D_Nonlinear(model, Ts=self.Ts)

        self.state = np.array([0, 0, 0, 0, 0, 0, 0])
        self.input = np.array([0, 0])

        self.sys_linear_cont = control.StateSpace(self.linear_dynamics.A, self.linear_dynamics.B,
                                                  self.linear_dynamics.C,
                                                  self.linear_dynamics.D, remove_useless_states=False)
        self.sys_linear_discrete = control.c2d(self.sys_linear_cont, 0.01)

        self.state_ctrl_K = np.hstack((np.zeros((2, 1)), self.linear_dynamics.K))

        K_2D = [0, self.state_ctrl_K[0][2], self.state_ctrl_K[0][3], self.state_ctrl_K[0][4]]
        self.linear_dynamics_2d = BILBO_Dynamics_2D_Linear(self.model, self.Ts, K_2D)

    def getP(self, N):
        return calc_transition_matrix(self.linear_dynamics_2d.sys_disc, N)

    @staticmethod
    def getLearningMatrices(r, s, P):
        N = P.shape[0]
        Qw = np.eye(N)
        Rw = r * np.eye(N)
        Sw = s * np.eye(N)
        Q, L = qlearning(P, Qw, Rw, Sw)
        return Q, L

    def _controller(self, state: np.ndarray, input: np.ndarray):
        input = np.asarray(input)
        output = input - self.state_ctrl_K @ state
        return output

    def _step(self, input):

        if isinstance(input, float):
            input = np.ndarray([input / 2, input / 2])

        output_controller = self._controller(self.state, input)

        if self.mode == 'nonlinear':
            self.state = self.nonlinear_dynamics.step(self.state, output_controller)
        elif self.mode == 'linear':
            self.state = self.linear_dynamics.step(self.state, output_controller)

    def simulate(self, steps, input, x0=None):

        assert (len(x0) == 7) if x0 is not None else True, "x0 must be of length 7"

        if x0 is not None:
            self.state = x0

        assert len(input) == steps, "Input must be of length steps"

        # states = [self.state]
        states = []

        for i in range(steps):
            self._step(input[i])
            states.append(self.state)

        return states


def test_bilbo_simulation():
    bilbo = BILBO(mode='nonlinear')
    N = len(bilbo_example_reference)

    P = bilbo.getP(N)
    Q, L = bilbo.getLearningMatrices(r=0.1, s=0.1, P=P)
    J = 15
    x0 = np.zeros((7,))

    u = np.zeros((N, 1))

    theta_trials = []
    e_norm = []

    for i in range(J):
        # Simulate
        states = bilbo.simulate(N, u, x0)

        # Get theta
        theta = np.asarray([state[3] for state in states])

        # Calculate the error
        error = (bilbo_example_reference - theta).reshape(N, 1)
        u = Q @ (u + L @ error)

        e_norm.append(np.linalg.norm(error))

        theta_trials.append(theta)

    plt.figure()

    for i in range(J):
        # alpha goes from very faint (0.1) up to almost opaque (1.0)
        α = 0.1 + 0.9 * (i / (J - 1))
        if i == 0 or i == J - 1 or i % 5 == 0:
            label = f'Trial {i+1}'
        else:
            label = '_nolegend_'
        plt.plot(theta_trials[i], color='red', alpha=α, label=label)

    plt.plot(bilbo_example_reference, label='Reference', color='k', linestyle='dashed')
    plt.legend()
    plt.grid()
    plt.xlabel("Time [s]")
    plt.ylabel("Theta [rad]")
    plt.title("ILC Progression")
    plt.show()

    plt.figure()
    plt.plot(e_norm, marker='o')
    plt.grid()
    plt.xticks(np.arange(1, J, 1))
    plt.xlabel("Trial")
    plt.xlim(left=0)
    plt.ylabel("Error Norm")
    plt.title("Error Norm")
    plt.ylim(top=e_norm[0])
    plt.show()


if __name__ == '__main__':
    test_bilbo_simulation()
