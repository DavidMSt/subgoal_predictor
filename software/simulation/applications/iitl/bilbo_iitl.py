import copy

import numpy as np
import matplotlib.pyplot as plt

from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS
from extensions.simulation._archive.bilbo import BILBO_DynamicAgent, BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS, \
    BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES, DEFAULT_BILBO_MODEL, BILBO_Dynamics_2D_Linear
from extensions.simulation.src.utils import lib_control
from extensions.simulation.utils.data import generate_time_vector, fun_sample_random_input


# ======================================================================================================================
def generate_learning_set(source_agent: BILBO_DynamicAgent, L, N, dt, f_cutoff=3, sigma_I=1):
    learning_set = {}
    T_end = (N - 1) * dt
    t_vector = generate_time_vector(0, T_end, dt)

    input_vectors = [None] * L
    output_vectors = [None] * L

    for l in range(L):
        input_vectors[l] = fun_sample_random_input(t_vector=t_vector,
                                                   f_cutoff=f_cutoff,
                                                   sigma_I=sigma_I)

        agent_input = BILBO_DynamicAgent.get3DInputFrom2D(input_vectors[l])
        agent_output = source_agent.simulate(input=agent_input)

        theta = [state['theta'].value for state in agent_output]
        output_vectors[l] = theta

        learning_set[l] = {
            'input': input_vectors[l],
            'output': output_vectors[l]
        }

        plt.plot(t_vector, np.rad2deg(theta), label=f'Output {l}')
        plt.plot(t_vector, input_vectors[l], label=f'Input {l}')
        plt.legend()
        plt.grid()
        plt.show()

    return learning_set


# ======================================================================================================================
class BILBO_IITL_Agent(BILBO_DynamicAgent):
    N: int  # Length of the reference trajectory
    k: int  # Index in the reference trajectory
    j: int  # Trial Index
    J: int  # Number of Trials

    r: float  # IITL design parameter
    s: float  # IITL design parameter

    u_j: np.ndarray  # Input Trajectory in the current trial
    y_j: np.ndarray  # Output of the current trial
    e_j: np.ndarray  # Error of the current trial

    t_j: np.ndarray  # Current Approximation of T

    data: dict

    L_j: np.ndarray  # Learning Matrix for the current trial
    Q_j: np.ndarray  # Q-Filter for the current trial

    learning_set: dict

    # ==================================================================================================================
    def __init__(self, agent_id,
                 poles=None,
                 model=None,
                 reference: [list, np.ndarray] = None,
                 J: int = 20,
                 r: float = 0.01,
                 s: float = 0.1,
                 *args,
                 **kwargs):
        if poles is None:
            poles = BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES

        eigenvectors = BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS

        if model is None:
            model = DEFAULT_BILBO_MODEL

        super().__init__(agent_id,
                         speed_control=False,
                         poles=poles,
                         eigenvectors=eigenvectors,
                         model=model,
                         *args, **kwargs)

        # ILC Parameters

        self.N = len(self.reference)
        self.k = 0
        self.j = 0
        self.J = J
        self.r = r
        self.s = s

        # Initialize the input and output
        self.u_j = np.zeros_like(self.reference)
        self.y_j = np.zeros_like(self.reference)
        self.e_j = np.zeros_like(self.reference)

        # Generate the 2D Dynamics for Learning
        self.dynamics_2d_linear = BILBO_Dynamics_2D_Linear(model=self.model,
                                                           Ts=self.Ts,
                                                           poles=[self.poles[0], self.poles[1], self.poles[2], self.poles[3]])

        # Initialize Learning Parameters
        self.L_j, self.Q_j = self.calculateLearningMatrices(self.r, self.s)

        self.trial_data = []

        # Add functions to certain phases
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.INPUT].addAction(self.calculateStepInput)
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT].addAction(self.appendOutput)

    # ==================================================================================================================
    def calculateLearningMatrices(self, r, s):
        # Calculate the transition matrix using the discrete-time linear model.
        P = lib_control.calc_transition_matrix(self.dynamics_2d_linear.sys, self.N)
        Qw = np.eye(self.N)
        Rw = r * np.eye(self.N)
        Sw = s * np.eye(self.N)
        Q, L = lib_control.qlearning(P, Qw, Rw, Sw)

        return L, Q

    # ==================================================================================================================
    def calculateStepInput(self):
        self.input = [self.u_j[self.k] / 2, self.u_j[self.k] / 2]

    # ==================================================================================================================
    def appendOutput(self):
        theta = self.state['theta'].value
        self.y_j[self.k] = theta
        self.k += 1

    # ==================================================================================================================
    def ilcUpdate(self):

        # Compute Error Signal
        self.e_j = self.reference - self.y_j

        # Save the trial data
        self.trial_data.append({
            'j': self.j,
            'u': copy.copy(self.u_j),
            'y': copy.copy(self.y_j),
            'e': copy.copy(self.e_j),
            'e_norm': np.linalg.norm(self.e_j)})

        # Update the ILC
        self.u_j = self.Q_j @ (self.u_j + self.L_j @ self.e_j)

        self.j += 1

    # ==================================================================================================================
    def runTrial(self):
        self.k = 0
        self.simulate(steps=self.N)
        self.ilcUpdate()

    # ==================================================================================================================
    def run(self, J):
        self.j = 0
        self.J = J
        while self.j < self.J:
            self.runTrial()
        return self.trial_data
