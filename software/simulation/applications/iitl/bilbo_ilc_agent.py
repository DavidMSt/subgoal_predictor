import copy

import numpy as np
import matplotlib.pyplot as plt

from extensions.simulation.src import core
from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS
from extensions.simulation._archive.bilbo import BILBO_DynamicAgent, BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS, \
    BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES, DEFAULT_BILBO_MODEL, BILBO_Dynamics_2D_Linear
from extensions.simulation.src.utils import lib_control


class BILBO_ILC_Agent(BILBO_DynamicAgent):
    N: int  # Length of the reference trajectory
    k: int  # Index in the reference trajectory
    j: int  # Trial Index
    J: int  # Number of Trials

    r: float  # ILC design parameter
    s: float  # ILC design parameter

    u_j: np.ndarray  # Input Trajectory in the current trial
    y_j: np.ndarray  # Output of the current trial
    e_j: np.ndarray  # Error of the current trial

    trial_data: list
    initial_state: core.spaces.State  # Initial state for all trials

    L_j: np.ndarray  # Learning Matrix for the current trial
    Q_j: np.ndarray  # Q-Filter for the current trial

    ref_j: np.ndarray  # Trial reference

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
        self.reference = np.asarray(reference)
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


bilbo_example_reference = [0, 0.000197760222250443, 2.11803678398722e-05, -0.00192431976122926,
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
                           0.00062972961798011, 0.00103310868987361, -4.31887979877787e-05]


def example_bilbo_ilc():
    agent = BILBO_ILC_Agent(agent_id='bilbo1',
                            reference=bilbo_example_reference,
                            J=20,
                            r=0,
                            s=0.0001)

    trial_data = agent.run(J=200)

    e_norm = [trial['e_norm'] for trial in trial_data]

    # plt.plot(e_norm)
    # plt.show()

    plt.plot(trial_data[-1]['y'], label='y')
    plt.plot(bilbo_example_reference, label='reference')
    plt.legend()
    plt.show()

    pass


if __name__ == '__main__':
    example_bilbo_ilc()

#
# # -----------------------------------------------------------------------------
# # BILBO ILC AGENT (ITERATIVE LEARNING CONTROL)
# # -----------------------------------------------------------------------------
# class BILBO_ILC_Agent(BILBO_DynamicAgent):
#     """
#     BILBO agent that implements Iterative Learning Control (ILC) over a series of trials.
#     """
#     # Reference trajectory and trial-related variables.
#     reference: np.ndarray  # Reference trajectory (desired output)
#     K: int  # Length of the reference trajectory
#     j: int  # Current trial number
#     k: int  # Current sample index within the trial
#     u_j: np.ndarray  # Current input trajectory for the trial
#     y_j: np.ndarray  # Measured output trajectory
#     e_j: np.ndarray  # Error trajectory
#     trials: list  # List to store data from previous trials
#     J_max: int = 20  # Maximum number of trials
#     initial_state: core.spaces.State  # Initial state for each trial
#
#     collision_during_trial: bool
#     L: np.ndarray  # Learning matrix
#     Q: np.ndarray  # Q filter matrix
#     wait_steps: int
#     trial_state: str  # 'trial', 'wait_before_trial', or 'wait_after_trial'
#     learning_finished_flag: bool
#     learning_successful: bool
#     dynamics_2d_linear: BILBO_2D_Linear
#
#     def __init__(self, env, agent_id, reference: np.ndarray, wait_steps: int = 50,
#                  r: float = 0.001, s: float = 0.1, initial_state: list = None,
#                  *args, **kwargs):
#         super().__init__(env=env, agent_id=agent_id)
#         self.reference = np.asarray(reference)
#         self.K = len(self.reference)
#         self.j = 0
#         self.k = 0
#         # Initialize input trajectory with random noise.
#         self.u_j = np.random.normal(0, scale=1, size=self.reference.shape)
#         self.y_j = np.zeros_like(self.reference)
#         self.wait_steps = wait_steps
#         self.collision_during_trial = False
#         self.trials = []
#         self.r = r
#         self.s = s
#         if initial_state is None:
#             initial_state = [-0.35, 0, 0, 0, 0, 0, 0]
#         self.initial_state = self.dynamics.state_space.map(initial_state)
#         self.state = self.initial_state
#         self.trial_state = 'wait_before_trial'
#         self.learning_finished_flag = False
#         self.learning_successful = False
#         # Instantiate the 2D linear model for ILC using provided model parameters.
#         self.dynamics_2d_linear = BILBO_2D_Linear(model=DEFAULT_BILBO_MODEL, Ts=DEFAULT_SAMPLE_TIME,
#                                                   poles=[0, -20, -3 + 1j, -3 - 1j])
#         self.setILC(r, s)
#         core.scheduling.Action(id='input', object=self, function=self._action_input)
#         core.scheduling.Action(id='logic2', object=self, function=self.update_after_step)
#
#     def setILC(self, r, s):
#         # Calculate the transition matrix using the discrete-time linear model.
#         P = lib_control.calc_transition_matrix(self.dynamics_2d_linear.sys_disc, self.K)
#         Qw = np.eye(self.K)
#         Rw = r * np.eye(self.K)
#         Sw = s * np.eye(self.K)
#         self.Q, self.L = lib_control.qlearning(P, Qw, Rw, Sw)
#
#     def update_after_step(self):
#         if self.k == self.K - 1:
#             self.update_after_trial()
#         else:
#             self.y_j[self.k] = self.state['theta'].value
#             if self.trial_state == 'trial':
#                 self.collision_during_trial = self.collision_during_trial or self.physics.collision.collision_state
#                 if self.collision_during_trial:
#                     setBabylonSettings(background_color=[242 / 255, 56 / 255, 56 / 255])
#             self.k += 1
#
#     def update_after_trial(self):
#         if self.learning_finished_flag:
#             return
#         # Compute error signal.
#         self.e_j = self.reference - self.y_j
#         # Save trial data.
#         self.trials.append({
#             'u': copy.copy(self.u_j),
#             'y': copy.copy(self.y_j),
#             'e': copy.copy(self.e_j),
#             'e_norm': np.linalg.norm(self.e_j),
#             'collision': self.collision_during_trial
#         })
#         # Check for successful trial.
#         if not self.collision_during_trial and self.state['x'].value > 0.0:
#             self.learning_finished_flag = True
#             self.learning_successful = True
#             setBabylonSettings(status=f"Trial {self.j}: Learning successful")
#             setBabylonSettings(background_color=[29 / 255, 145 / 255, 31 / 255])
#             save_data = {
#                 'trials': self.trials,
#                 'reference': self.reference,
#                 's': self.s,
#                 'r': self.r,
#                 'success': self.learning_successful
#             }
#             with open("ilc_data.p", "wb") as filehandler:
#                 pickle.dump(save_data, filehandler)
#         if self.j == self.J_max - 1:
#             # Maximum trials reached; mark failure.
#             self.learning_finished_flag = True
#             self.learning_successful = False
#             plt.plot(self.trials[-1]['y'])
#             plt.plot(self.reference)
#             setBabylonSettings(status=f"Trial {self.j}: Learning failed")
#             save_data = {
#                 'trials': self.trials,
#                 'reference': self.reference,
#                 's': self.s,
#                 'r': self.r,
#                 'success': self.learning_successful
#             }
#             with open("ilc_data.p", "wb") as filehandler:
#                 pickle.dump(save_data, filehandler)
#         # Update the input trajectory using the ILC update law.
#         self.u_j = self.Q @ (self.u_j + self.L @ self.e_j)
#         self.j += 1
#         self.trial_state = 'wait_after_trial'
#         self.collision_during_trial = False
#         self.k = 0
#
#     def _action_input(self):
#         print("INPUT")
#         if not self.learning_finished_flag:
#             if self.trial_state == 'trial':
#                 self.input = [self.u_j[self.k] / 2, self.u_j[self.k] / 2]
#             elif self.trial_state in ('wait_after_trial', 'wait_before_trial'):
#                 self.input = [0, 0]
#         else:
#             self.input = [0, 0]
#
#     def _action_entry(self, *args, **kwargs):
#         super()._action_entry(*args, **kwargs)
#         if self.j == 0:
#             setBabylonSettings(status="Trial 0")
#         if not self.learning_finished_flag:
#             if self.trial_state == 'wait_before_trial' and self.k == self.wait_steps:
#                 self.k = 0
#                 self.trial_state = 'trial'
#             elif self.trial_state == 'wait_after_trial' and self.k == self.wait_steps:
#                 self.k = 0
#                 self.trial_state = 'wait_before_trial'
#                 self.state = copy.copy(self.initial_state)
#                 self.setPosition(x=self.state['x'])
#                 setBabylonSettings(status=f"Trial {self.j}")
#                 setBabylonSettings(background_color=0)
#
#     def _action_exit(self, *args, **kwargs):
#         super()._action_exit(*args, **kwargs)
