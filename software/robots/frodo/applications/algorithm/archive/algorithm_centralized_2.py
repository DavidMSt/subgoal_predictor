from __future__ import annotations

import dataclasses
import math
import enum

import numpy as np

from core.utils.logging_utils import Logger


class AlgorithmState(enum.StrEnum):
    RUNNING = 'RUNNING'
    STOPPED = 'STOPPED'


AGENT_STATE_DIM = 4
INDEX_X = 0
INDEX_Y = 1
INDEX_SIN = 2
INDEX_COS = 3

INDEX_PSI = 2

INDEX_V = 0
INDEX_PSIDOT = 1


def unscented_transform_psi_to_sin_cos(mean_psi: float, var_psi: float):
    """
    Applies the unscented transform to compute the mean and covariance of [sin(ψ), cos(ψ)]
    from the mean and variance of ψ.
    """

    # UT parameters
    n = 1  # dimension of ψ
    alpha = 1e-3
    beta = 2.0
    kappa = 0.0
    lambda_ = alpha ** 2 * (n + kappa) - n

    # Weights
    wm = np.zeros(2 * n + 1)
    wc = np.zeros(2 * n + 1)
    wm[0] = lambda_ / (n + lambda_)
    wc[0] = lambda_ / (n + lambda_) + (1 - alpha ** 2 + beta)
    for i in range(1, 2 * n + 1):
        wm[i] = wc[i] = 1.0 / (2 * (n + lambda_))

    # Sigma points for ψ
    sqrt_c = np.sqrt((n + lambda_) * var_psi)
    sigma_points = np.array([
        mean_psi,
        mean_psi + sqrt_c,
        mean_psi - sqrt_c
    ])

    # Transform to [sin(ψ), cos(ψ)]
    transformed = np.array([[np.sin(psi), np.cos(psi)] for psi in sigma_points])  # shape (3, 2)

    # Mean
    mean_trans = np.sum(wm[:, np.newaxis] * transformed, axis=0)

    # Covariance
    diff = transformed - mean_trans
    cov_trans = sum(wc[i] * np.outer(diff[i], diff[i]) for i in range(2 * n + 1))

    return mean_trans, cov_trans


@dataclasses.dataclass
class AlgorithmAgentState:
    x: float
    y: float
    psi: float

    def as_array(self):
        return np.array([self.x, self.y, self.psi])

    @staticmethod
    def from_array(array):
        return AlgorithmAgentState(array[0], array[1], array[2])


@dataclasses.dataclass
class AlgorithmAgentUncertainty:
    ...


@dataclasses.dataclass
class AlgorithmAgentInput:
    v: float = 0.0
    psi_dot: float = 0.0

    def as_array(self):
        return np.array([self.v, self.psi_dot])

    @classmethod
    def from_array(cls, array):
        new_input = cls()
        new_input.v = array[0]
        new_input.psi_dot = array[1]
        return new_input


@dataclasses.dataclass
class AlgorithmAgentMeasurement:
    source: FRODO_AlgorithmAgent
    source_index: int
    target: FRODO_AlgorithmAgent
    target_index: int
    measurement: np.ndarray
    measurement_covariance: np.ndarray

    @property
    def measurement_augmented(self):
        return np.array([
            self.measurement[0],
            self.measurement[1],
            np.sin(self.measurement[2]),
            np.cos(self.measurement[2]),
        ])

    @property
    def measurement_covariance_augmented(self):
        P = self.measurement_covariance
        psi_hat = float(self.measurement[2])
        var_psi = float(P[2, 2])

        _, cov_sin_cos = unscented_transform_psi_to_sin_cos(psi_hat, var_psi)

        # Build full 4x4 augmented covariance matrix
        P_aug = np.zeros((4, 4))
        P_aug[0, 0] = P[0, 0]
        P_aug[1, 1] = P[1, 1]
        P_aug[2:4, 2:4] = cov_sin_cos

        return P_aug


@dataclasses.dataclass
class FRODO_AlgorithmAgent:
    id: str
    state: AlgorithmAgentState
    state_covariance: np.ndarray
    index: int = 0
    input: AlgorithmAgentInput = dataclasses.field(default_factory=AlgorithmAgentInput)
    dynamics_noise_floor: float = 1e-4
    is_anchor: bool = False
    measurements: list[AlgorithmAgentMeasurement] = dataclasses.field(default_factory=list)

    @property
    def state_augmented(self):
        return np.array([
            self.state.x,
            self.state.y,
            np.sin(self.state.psi),
            np.cos(self.state.psi),
        ])

    @property
    def state_covariance_augmented(self):
        # Extract heading mean and variance
        psi_hat = self.state.psi
        P = self.state_covariance
        var_psi = P[2, 2]

        # First-order Jacobian
        J = np.array([
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, np.cos(psi_hat)],
            [0, 0, -np.sin(psi_hat)]
        ])

        # Initial linearized covariance
        P_aug = J @ P @ J.T

        # Second-order corrections for sin(psi) and cos(psi)
        sin_psi = np.sin(psi_hat)
        cos_psi = np.cos(psi_hat)

        var_sin = (cos_psi ** 2) * var_psi + 0.5 * (sin_psi ** 2) * (var_psi ** 2)
        var_cos = (sin_psi ** 2) * var_psi + 0.5 * (cos_psi ** 2) * (var_psi ** 2)

        # Optional: Covariance between sin and cos (can be helpful if needed)
        cov_sin_cos = -sin_psi * cos_psi * var_psi \
                      + 0.5 * sin_psi * cos_psi * (cos_psi ** 2 - sin_psi ** 2) * (var_psi ** 2)

        # Apply the corrections
        P_aug[2, 2] = var_sin
        P_aug[3, 3] = var_cos
        P_aug[2, 3] = cov_sin_cos
        P_aug[3, 2] = cov_sin_cos  # symmetric

        return P_aug


class CentralizedLocationAlgorithm:
    agents: dict[str, FRODO_AlgorithmAgent]

    Ts: float
    state: np.ndarray
    state_covariance: np.ndarray
    step: int = 0

    x_hat_pre: np.ndarray = None
    P_hat_pre: np.ndarray = None

    def __init__(self, Ts):
        self.Ts = Ts

        if abs(Ts) < 1e-5:
            raise ValueError("Ts must be greater than 0")

        self.logger = Logger("CEKF", "DEBUG")

    # ------------------------------------------------------------------------------------------------------------------
    def init(self, agents: list[FRODO_AlgorithmAgent]):
        # Build the agent dictionary
        self.agents = {}

        for i, agent in enumerate(agents):
            self.agents[agent.id] = agent
            agent.index = i

        # Build the state
        self.state = np.zeros(len(agents) * AGENT_STATE_DIM)
        for i, agent in enumerate(self.agents.values()):
            self.state[i * AGENT_STATE_DIM:(i + 1) * AGENT_STATE_DIM] = agent.state_augmented

        # Build the state covariance
        self.state_covariance = np.zeros((len(agents) * 4, len(agents) * 4))
        for i, agent in enumerate(self.agents.values()):
            self.state_covariance[
                i * AGENT_STATE_DIM:(i + 1) * AGENT_STATE_DIM,
                i * AGENT_STATE_DIM:(i + 1) * AGENT_STATE_DIM
            ] = agent.state_covariance_augmented

        # Log initialization info
        self.logger.info(f"Algorithm initialized with {len(agents)} agents.")

        # Beautified formatted printing for arrays
        with np.printoptions(precision=2, suppress=True):
            self.logger.info(f"Initial state:\n{self.state}")
            # self.logger.debug(f"State covariance:\n{self.state_covariance}")

    # ------------------------------------------------------------------------------------------------------------------
    def prediction(self):
        self.x_hat_pre, self.P_hat_pre = self._prediction()

    # ------------------------------------------------------------------------------------------------------------------
    def update(self):

        if self.P_hat_pre is None:
            print("GOT A BIG PROBLEM")
            return

        # STEP 2: EXTRACT MEASUREMENTS
        measurements = self.getMeasurements()
        measurement_list = [f"{measurement.source}->{measurement.target}" for measurement in measurements]

        if len(measurements) > 0:

            # STEP 3: CALCULATE SPARSE MEASUREMENT JACOBIAN
            H = self.measurementJacobian_sparse(measurements)

            # H[:,0:4] = np.zeros((4,4))
            # STEP 4: CALCULATE THE KALMAN GAIN
            W = self.buildMeasurementCovariance_sparse(measurements)
            K = self.P_hat_pre @ H.T @ np.linalg.inv(H @ self.P_hat_pre @ H.T + W)

            # STEP 5: BUILD THE MEASUREMENT VECTOR
            y = self.buildMeasurementVector_sparse(measurements)

            # STEP 6: BUILD THE PREDICTED MEASUREMENT VECTOR
            y_est = self.measurementPrediction_sparse(measurements)

            # STEP 7: UPDATE
            diff = y - y_est

            # correction_term = K @ diff
            new_state = self.x_hat_pre + K @ diff
            new_covariance = (np.eye(len(self.agents) * AGENT_STATE_DIM) - K @ H) @ self.P_hat_pre @ (
                    np.eye(len(self.agents) * AGENT_STATE_DIM) - K @ H).T + K @ W @ K.T

            # --- SANITY CHECK: update identity & PSD ---
            chk_upd = check_update(self.P_hat_pre, H, W, K, new_covariance, tag="upd/full")
            if not chk_upd["ok"]:
                self.logger.warning(
                    f"[{chk_upd['tag']}] resid_fro={chk_upd['resid_fro']:.2e} "
                    f"| minEig(S)={chk_upd['min_eig_S']:.2e} "
                    f"| minEig(P_post)={chk_upd['min_eig_Ppost']:.2e}"
                )

        else:
            new_state = self.x_hat_pre
            new_covariance = self.P_hat_pre

        self.state = new_state
        self.state_covariance = new_covariance

        # # Write the state back to the agents
        for i in range(len(self.agents)):
            agent = self.getAgentByIndex(i)
            if agent is None:
                raise ValueError(f"Agent with index {i} does not exist.")

            state = self.state[i * AGENT_STATE_DIM:(i + 1) * AGENT_STATE_DIM]
            agent.state.x = float(state[INDEX_X])
            agent.state.y = float(state[INDEX_Y])
            agent.state.psi = float(np.arctan2(state[INDEX_SIN], state[INDEX_COS]))

            state_covariance_aug = self.state_covariance[i * AGENT_STATE_DIM:(i + 1) * AGENT_STATE_DIM,
            i * AGENT_STATE_DIM:(i + 1) * AGENT_STATE_DIM]

            s = state[INDEX_SIN]
            c = state[INDEX_COS]
            r2 = s * s + c * c
            J = np.array([
                [1, 0, 0, 0],
                [0, 1, 0, 0],
                [0, 0, c / r2, -s / r2],
            ])

            prev_covariance_aug = agent.state_covariance_augmented

            prev_covariance = agent.state_covariance
            agent.state_covariance = J @ state_covariance_aug @ J.T

            # if self._is_agent_deadreckoning(agent):
            #     if not self._covariance_increased(prev_covariance, agent.state_covariance):
            #         self.logger.warning(f"Oh Oh. Covariance did not increase for agent {agent.id}.")

        self.step += 1

        if (self.step % 10) == 0 or self.step == 1:
            print("--------------------------------")
            print(f"Step: {self.step}")
            for agent in self.agents.values():
                print(
                    f"{agent.id}: \t x: {agent.state.x:.3f} \t y: {agent.state.y:.3f} \t psi: {agent.state.psi:.2f} \t Cov: {np.linalg.norm(agent.state_covariance, 'fro'):.1f}")

            pass

    # ------------------------------------------------------------------------------------------------------------------
    def reset(self):
        self.agents = {}
        self.step = 0

    # ------------------------------------------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------------------------------------------
    # def augmentAgentState(self, state):
    #
    #     state = np.asarray(state)
    #     assert (len(state) == 3)
    #
    #     augmented_state = np.array([
    #         state[0],
    #         state[1],
    #         np.sin(state[2]),
    #         np.cos(state[2]),
    #     ])
    #
    #     return augmented_state

    # ------------------------------------------------------------------------------------------------------------------
    def augmentAgentCovariance(self, covariance):
        return covariance

    # ------------------------------------------------------------------------------------------------------------------
    def predictionAgent(self, state: np.ndarray, input: np.ndarray):
        """
        Prediction step of one agent
        Args:
            state: State of the agent
            input: Input to the agent

        Returns:

        """

        state_hat = np.array([
            state[INDEX_X] + self.Ts * input[INDEX_V] * state[INDEX_COS],
            state[INDEX_Y] + self.Ts * input[INDEX_V] * state[INDEX_SIN],
            state[INDEX_SIN] + self.Ts * input[INDEX_PSIDOT] * state[INDEX_COS],
            state[INDEX_COS] - self.Ts * input[INDEX_PSIDOT] * state[INDEX_SIN]
        ])

        return state_hat

    # ------------------------------------------------------------------------------------------------------------------
    def enumerateAgentArray(self):
        """
        Enumerate the agents in the array
        Returns:

        """
        for i, agent in enumerate(self.agents.values()):
            agent.index = i

    # ------------------------------------------------------------------------------------------------------------------
    def getMeasurements(self):
        measurements = []

        for i in range(len(self.agents)):
            agent = self.getAgentByIndex(i)
            if agent is None:
                raise ValueError(f"Agent with index {i} does not exist.")

            if len(agent.measurements) > 0:
                measurements.extend(agent.measurements)

        return measurements

    # ------------------------------------------------------------------------------------------------------------------
    def _prediction(self):
        """
        Calculate the prediction of the full system
        Returns:

        """

        # Predict the states
        x_hat = np.zeros(len(self.agents) * AGENT_STATE_DIM)
        for i in range(len(self.agents)):
            agent = self.getAgentByIndex(i)
            if agent is None:
                raise ValueError(f"Agent with index {i} does not exist.")
            x_hat[i * AGENT_STATE_DIM:(i + 1) * AGENT_STATE_DIM] = self.predictionAgent(agent.state_augmented,
                                                                                        agent.input.as_array())

        # Calculate the dynamics jacobian
        F = self.dynamicsJacobian()

        Q = np.zeros_like(self.state_covariance)
        q_floor = 1e-12

        for i in range(len(self.agents)):
            agent = self.getAgentByIndex(i)
            sl = slice(i * AGENT_STATE_DIM, (i + 1) * AGENT_STATE_DIM)

            G = self.input_jacobian_agent(agent.state_augmented)

            Ru = self.input_covariance_from_input(agent.input, agent.is_anchor)

            Qi = G @ Ru @ G.T
            # add per-agent state-space floor; zero for anchors
            if not agent.is_anchor:
                Qi += agent.dynamics_noise_floor * np.eye(AGENT_STATE_DIM)
                # (optional) tiny global numerical floor to avoid singularities
                Qi += q_floor * np.eye(AGENT_STATE_DIM)

            Q[sl, sl] = Qi

        P_prev = self.state_covariance.copy()
        P_hat = F @ self.state_covariance @ F.T + Q

        # --- SANITY CHECK: prediction identity & PSD ---
        chk = check_prediction(P_prev, F, Q, P_hat, tag="pred/full")
        if not chk["ok"]:
            self.logger.warning(
                f"[{chk['tag']}] resid_fro={chk['resid_fro']:.2e} "
                f"| minEig(P_pred)={chk['min_eig_Ppred']:.2e} "
                f"| minEig(Q)={chk['min_eig_Q']:.2e}"
            )

        # (optional but recommended) symmetrize to kill tiny asymmetry
        P_hat = 0.5 * (P_hat + P_hat.T)

        return x_hat, P_hat

    # ------------------------------------------------------------------------------------------------------------------
    def jacobianAgent(self, state: np.ndarray, input: np.ndarray):
        """
        Calculate the Jacobian matrix of the agent's motion model
        Args:
            state:
            input:

        Returns:

        """
        F = np.array([
            [1, 0, 0, self.Ts * input[INDEX_V]],
            [0, 1, self.Ts * input[INDEX_V], 0],
            [0, 0, 1, self.Ts * input[INDEX_PSIDOT]],
            [0, 0, -self.Ts * input[INDEX_PSIDOT], 1]
        ])
        return F

    # ------------------------------------------------------------------------------------------------------------------
    def dynamicsJacobian(self):
        """
        Calculate the Jacobian matrix of the full system
        Returns:

        """
        J = np.zeros((len(self.agents) * AGENT_STATE_DIM, len(self.agents) * AGENT_STATE_DIM))

        for i in range(len(self.agents)):
            agent = self.getAgentByIndex(i)
            if agent is None:
                raise ValueError(f"Agent with index {i} does not exist.")
            J[i * AGENT_STATE_DIM:(i + 1) * AGENT_STATE_DIM, i * AGENT_STATE_DIM:(i + 1) * AGENT_STATE_DIM] = \
                self.jacobianAgent(agent.state_augmented, agent.input.as_array())

        return J

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def measurementPredictionAgent(agent_source_state_augmented, agent_target_state_augmented):

        x1 = agent_source_state_augmented[INDEX_X]
        y1 = agent_source_state_augmented[INDEX_Y]
        s1 = agent_source_state_augmented[INDEX_SIN]
        c1 = agent_source_state_augmented[INDEX_COS]

        x2 = agent_target_state_augmented[INDEX_X]
        y2 = agent_target_state_augmented[INDEX_Y]
        s2 = agent_target_state_augmented[INDEX_SIN]
        c2 = agent_target_state_augmented[INDEX_COS]

        h_source_target = np.array([
            [c1 * (x2 - x1) + s1 * (y2 - y1)],
            [-s1 * (x2 - x1) + c1 * (y2 - y1)],
            [s2 * c1 - c2 * s1],
            [c2 * c1 + s2 * s1],
        ])

        return h_source_target

    # ------------------------------------------------------------------------------------------------------------------
    def calculatePredictionCovariance(self, state_covariance, dynamics_jacobian, dynamics_noise_covariance):
        return dynamics_jacobian @ state_covariance @ dynamics_jacobian.T + dynamics_noise_covariance

    # ------------------------------------------------------------------------------------------------------------------
    # def measurementJacobian(self):
    #
    #     H = np.zeros((3 * (len(self.agents) ** 2), 3 * len(self.agents)))
    #
    #     for i in range(len(self.agents)):
    #         sub_H = np.zeros((3 * len(self.agents), 3 * len(self.agents)))
    #
    #         for ii in range(len(self.agents)):
    #             for jj in range(len(self.agents)):
    #                 if i == ii:
    #                     continue
    #
    #                 if jj == i:
    #                     H_agent = self.measurementJacobianAgents(self.getAgentByIndex(i), self.getAgentByIndex(ii), 1)
    #                     pass
    #                 elif ii == jj:
    #                     H_agent = self.measurementJacobianAgents(self.getAgentByIndex(i), self.getAgentByIndex(jj), 2)
    #                     pass
    #                 else:
    #                     continue
    #
    #                 sub_H[3 * ii:3 * (ii + 1), 3 * jj:3 * (jj + 1)] = H_agent
    #                 pass
    #
    #         H[3 * len(self.agents) * i:3 * len(self.agents) * (i + 1), :] = sub_H
    #     return H

    # ------------------------------------------------------------------------------------------------------------------
    def measurementJacobian_sparse(self, measurements):
        H = np.zeros((AGENT_STATE_DIM * len(measurements), AGENT_STATE_DIM * len(self.agents)))
        for i, m in enumerate(measurements):
            src_aug = self._xpre_agent_aug(m.source_index)
            tgt_aug = self._xpre_agent_aug(m.target_index)

            H_src = self.measurementJacobianAgents(src_aug, tgt_aug, reference_agent=1)
            H_tgt = self.measurementJacobianAgents(src_aug, tgt_aug, reference_agent=2)

            r = i * AGENT_STATE_DIM
            H[r:r + AGENT_STATE_DIM, m.source_index * AGENT_STATE_DIM:(m.source_index + 1) * AGENT_STATE_DIM] = H_src
            H[r:r + AGENT_STATE_DIM, m.target_index * AGENT_STATE_DIM:(m.target_index + 1) * AGENT_STATE_DIM] = H_tgt
        return H

    # ------------------------------------------------------------------------------------------------------------------
    def buildMeasurementCovariance_sparse(self, measurements: list[AlgorithmAgentMeasurement]) -> np.ndarray:
        W = np.zeros((AGENT_STATE_DIM * len(measurements), AGENT_STATE_DIM * len(measurements)))

        for i, measurement in enumerate(measurements):
            W_meas = np.eye(AGENT_STATE_DIM) @ measurement.measurement_covariance_augmented
            W[i * AGENT_STATE_DIM:(i + 1) * AGENT_STATE_DIM, i * AGENT_STATE_DIM:(i + 1) * AGENT_STATE_DIM] = W_meas

        return W

    # ------------------------------------------------------------------------------------------------------------------
    def buildMeasurementVector_sparse(self, measurements: list[AlgorithmAgentMeasurement]) -> np.ndarray:
        y = np.zeros(AGENT_STATE_DIM * len(measurements))

        for i, measurement in enumerate(measurements):
            y[i * AGENT_STATE_DIM:(i + 1) * AGENT_STATE_DIM] = measurement.measurement_augmented

        return y

    # ------------------------------------------------------------------------------------------------------------------
    def measurementPrediction_sparse(self, measurements: list[AlgorithmAgentMeasurement]) -> np.ndarray:
        y_est = np.zeros(AGENT_STATE_DIM * len(measurements))

        for i, measurement in enumerate(measurements):
            src_aug = self._xpre_agent_aug(measurement.source_index)
            tgt_aug = self._xpre_agent_aug(measurement.target_index)
            predicted_measurement = self.measurementPredictionAgent(src_aug, tgt_aug)

            # agent_source = self.getAgentByIndex(measurement.source_index)
            # agent_target = self.getAgentByIndex(measurement.target_index)
            #
            # predicted_measurement = self.measurementPredictionAgent(
            #     agent_source_state_augmented=agent_source.state_augmented,
            #     agent_target_state_augmented=agent_target.state_augmented)

            y_est[i * AGENT_STATE_DIM:(i + 1) * AGENT_STATE_DIM] = predicted_measurement.flatten()

        return y_est
    # ------------------------------------------------------------------------------------------------------------------
    def measurementJacobianAgents(self, src_aug: np.ndarray, tgt_aug: np.ndarray, reference_agent: int):
        x1, y1, s1, c1 = src_aug[INDEX_X], src_aug[INDEX_Y], src_aug[INDEX_SIN], src_aug[INDEX_COS]
        x2, y2, s2, c2 = tgt_aug[INDEX_X], tgt_aug[INDEX_Y], tgt_aug[INDEX_SIN], tgt_aug[INDEX_COS]

        if reference_agent == 1:
            return np.array([
                [-c1, -s1, y2 - y1, x2 - x1],
                [s1, -c1, -x2 + x1, y2 - y1],
                [0, 0, -c2, s2],
                [0, 0, s2, c2],
            ])
        else:  # reference_agent == 2
            return np.array([
                [c1, s1, 0, 0],
                [-s1, c1, 0, 0],
                [0, 0, c1, -s1],
                [0, 0, s1, c1],
            ])

    # ------------------------------------------------------------------------------------------------------------------
    def measurementPrediction(self):

        prediction_vector = np.zeros(3 * len(self.agents) ** 2)

        for i in range(len(self.agents)):
            agent_from = self.getAgentByIndex(i)
            if agent_from is None:
                raise ValueError(f"Agent with index {i} does not exist.")
            for j in range(len(self.agents)):
                agent_to = self.getAgentByIndex(j)
                if agent_to is None:
                    raise ValueError(f"Agent with index {j} does not exist.")

                if i == j:
                    continue

                predicted_measurement = self.measurementPredictionAgent(agent_from.state.as_array(),
                                                                        agent_to.state.as_array())
                prediction_vector[i * len(self.agents) * 3 + 3 * j:i * len(self.agents) * 3 + 3 * (
                        j + 1)] = predicted_measurement.flatten()
                pass

        return prediction_vector

    # ------------------------------------------------------------------------------------------------------------------
    def buildMeasurementVector(self):

        y = np.zeros(3 * len(self.agents) ** 2)
        for i in range(len(self.agents)):
            agent_from = self.getAgentByIndex(i)
            if agent_from is None:
                raise ValueError(f"Agent with index {i} does not exist.")

            for j in range(len(self.agents)):
                agent_to = self.getAgentByIndex(j)
                if agent_to is None:
                    raise ValueError(f"Agent with index {j} does not exist.")

                if i == j:
                    continue

                # Check if agent from has a measurement to agent_to in its measurements
                measurement_found = False
                measurement: AlgorithmAgentMeasurement = None
                for m in agent_from.measurements:
                    if m.target_index == j:
                        measurement_found = True
                        measurement = m
                        break

                if measurement_found:

                    y[i * len(self.agents) * 3 + 3 * j:i * len(self.agents) * 3 + 3 * (j + 1)] = measurement.measurement
                else:
                    continue

        return y

    def buildMeasurementCovariance(self):

        value_measurement_exists = 1e-5
        value_measurement_not_exists = 1e9

        W = 0 * np.ones((3 * len(self.agents) ** 2, 3 * len(self.agents) ** 2))

        for i in range(len(self.agents)):
            agent_from = self.getAgentByIndex(i)
            if agent_from is None:
                raise ValueError(f"Agent with index {i} does not exist.")

            for j in range(len(self.agents)):
                agent_to = self.getAgentByIndex(j)
                if agent_to is None:
                    raise ValueError(f"Agent with index {j} does not exist.")

                offset = len(self.agents) * 3 * i

                if i == j:
                    W[offset + 3 * j:offset + 3 * (j + 1), offset + 3 * j:offset + 3 * (j + 1)] = np.eye(
                        3) * value_measurement_not_exists
                    continue

                measurement_found = False
                measurement: AlgorithmAgentMeasurement = None
                for m in agent_from.measurements:
                    if m.target_index == j:
                        measurement_found = True
                        measurement = m
                        break

                if measurement_found:
                    W[offset + 3 * j:offset + 3 * (j + 1), offset + 3 * j:offset + 3 * (j + 1)] = np.eye(
                        3) * value_measurement_exists
                else:
                    W[offset + 3 * j:offset + 3 * (j + 1), offset + 3 * j:offset + 3 * (j + 1)] = np.eye(
                        3) * value_measurement_not_exists

        return W

    # ------------------------------------------------------------------------------------------------------------------

    def input_jacobian_agent(self, state_aug):
        c = state_aug[INDEX_COS]
        s = state_aug[INDEX_SIN]
        Ts = self.Ts
        G = np.array([
            [Ts * c, 0.0],
            [Ts * s, 0.0],
            [0.0, Ts * c],
            [0.0, -1.0 * Ts * s],
        ])
        return G

    # ------------------------------------------------------------------------------------------------------------------
    def _xpre_agent_aug(self, i: int) -> np.ndarray:
        """Predicted (k+1|k) augmented state [x, y, sinψ, cosψ] for agent i."""
        return self.x_hat_pre[i * AGENT_STATE_DIM:(i + 1) * AGENT_STATE_DIM]

    # ------------------------------------------------------------------------------------------------------------------
    def input_covariance_from_input(self, u: AlgorithmAgentInput, is_anchor: bool = False):
        if is_anchor:
            # Anchors: no input-driven process noise at all
            return np.zeros((2, 2))

        v = abs(u.v)
        w = abs(u.psi_dot)

        # Example: linear growth model
        sigma_v0, kv = 0.005, 1  # std_v = 0.005 + 0.10*|v|
        sigma_w0, kw = 0.002, 0.20  # std_w = 0.002 + 0.10*|w|

        # sigma_v0, kv = 0.01, 3 # std_v = 0.005 + 0.10*|v|
        # sigma_w0, kw = 0.01, 3  # std_w = 0.002 + 0.10*|w|

        std_v = sigma_v0 + kv * v
        std_w = sigma_w0 + kw * w
        return np.diag([std_v ** 2, std_w ** 2])

    # ------------------------------------------------------------------------------------------------------------------
    def getAgentByIndex(self, index: int) -> FRODO_AlgorithmAgent | None:
        for agent in self.agents.values():
            if agent.index == index:
                return agent
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def getAgentIndex(self, id: str) -> int | None:
        for i, agent in enumerate(self.agents.values()):
            if agent.id == id:
                return i
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def _is_agent_deadreckoning(self, agent: FRODO_AlgorithmAgent) -> bool:
        if len(agent.measurements) > 0:
            return False

        for other_agent in self.agents.values():
            for measurement in other_agent.measurements:
                if measurement.target == agent:
                    return False

        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _covariance_increased(self, cov_prev, cov) -> bool:
        tol = 1e-4
        diff = cov - cov_prev

        return np.all(np.linalg.eigvalsh(diff) >= -tol)


def is_psd(A, tol=1e-10):
    A = 0.5 * (A + A.T)  # symmetrize
    return np.linalg.eigvalsh(A).min() >= -tol


def fro_norm(A):
    return float(np.linalg.norm(0.5 * (A + A.T), ord='fro'))


def check_prediction(P_prev, F, Q, P_pred, tag="pred"):
    lhs = P_pred
    rhs = F @ P_prev @ F.T + Q
    resid = lhs - rhs
    ok = fro_norm(resid) <= 1e-8 * max(1.0, fro_norm(rhs))
    return {
        "ok": ok and is_psd(P_pred),
        "resid_fro": fro_norm(resid),
        "min_eig_Ppred": float(np.linalg.eigvalsh(0.5 * (P_pred + P_pred.T)).min()),
        "min_eig_Q": float(np.linalg.eigvalsh(0.5 * (Q + Q.T)).min()),
        "tag": tag,
    }


def check_update(P_pred, H, R, K, P_post, tag="upd"):
    S = H @ P_pred @ H.T + R
    rhs = (np.eye(P_pred.shape[0]) - K @ H) @ P_pred @ (np.eye(P_pred.shape[0]) - K @ H).T + K @ R @ K.T
    resid = P_post - rhs
    ok = fro_norm(resid) <= 1e-8 * max(1.0, fro_norm(rhs))
    return {
        "ok": ok and is_psd(S) and is_psd(P_post),
        "resid_fro": fro_norm(resid),
        "min_eig_S": float(np.linalg.eigvalsh(0.5 * (S + S.T)).min()),
        "min_eig_Ppost": float(np.linalg.eigvalsh(0.5 * (P_post + P_post.T)).min()),
        "tag": tag,
    }
