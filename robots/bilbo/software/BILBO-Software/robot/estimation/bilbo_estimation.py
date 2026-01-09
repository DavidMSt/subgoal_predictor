import ctypes
import dataclasses
import enum

import numpy as np

import robot.lowlevel.stm32_addresses as addresses
from robot.bilbo_common import BILBO_Common
from robot.bilbo_definitions import BILBO_DynamicState, BILBO_ConfigurationState
from robot.communication.bilbo_communication import BILBO_Communication
from robot.estimation.optitrack_tracker import BILBO_OptiTrackListener
from robot.lowlevel.stm32_sample import BILBO_LL_Sample
from core.utils.logging_utils import Logger


class TWIPR_Estimation_Status(enum.IntEnum):
    ERROR = 0,
    NORMAL = 1,


@dataclasses.dataclass(frozen=True)
class TWIPR_Estimation_Sample:
    status: TWIPR_Estimation_Status = dataclasses.field(default=TWIPR_Estimation_Status.NORMAL)
    state: BILBO_DynamicState = dataclasses.field(default_factory=BILBO_DynamicState)
    state_optitrack: BILBO_ConfigurationState = dataclasses.field(default_factory=BILBO_ConfigurationState)


# ======================================================================================================================
class BILBO_Estimation:
    _comm: BILBO_Communication

    state: BILBO_DynamicState
    status: TWIPR_Estimation_Status
    tracker: BILBO_OptiTrackListener

    def __init__(self, common: BILBO_Common, comm: BILBO_Communication):
        self._comm = comm
        self.common = common
        self.state = BILBO_DynamicState()

        self.tracker = BILBO_OptiTrackListener(common=self.common)
        self.tracker.callbacks.sample.register(self._on_tracker_sample_callback)

        self.status = TWIPR_Estimation_Status.NORMAL
        self._comm.events.rx_stm32_sample.on(self._onSample)
        # self._comm.callbacks.rx_stm32_sample.register(self._onSample)

        self.logger = Logger('Estimation')
        self.logger.setLevel('DEBUG')

    # ==================================================================================================================
    def init(self):
        theta_offset = self.common.config.model.theta_offset
        self.setThetaOffset(theta_offset)
        self.tracker.init()


    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.tracker.start()

    # ------------------------------------------------------------------------------------------------------------------
    def getSample(self) -> TWIPR_Estimation_Sample | dict:
        raise NotImplementedError

    # ------------------------------------------------------------------------------------------------------------------
    def _on_tracker_sample_callback(self, sample: BILBO_ConfigurationState):
        self.state.x = sample.x
        self.state.y = sample.y
        self.state.psi = sample.psi

        print(f"Position: {self.state.x:.2f} {self.state.y:.2f}, Orientation: {self.state.psi:.2f}")

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample_dict(self) -> dict:
        tracker_state = self.tracker.get_state()

        if tracker_state is None:
            tracker_state = BILBO_ConfigurationState()

        tracker_state = dataclasses.asdict(tracker_state)

        sample = {
            'status': self.status,
            'state': dataclasses.asdict(self.state),
            'state_optitrack': tracker_state,
        }
        return sample

    # ------------------------------------------------------------------------------------------------------------------
    def setThetaOffset(self, offset: float):
        self.logger.info(f'Setting theta offset to {np.rad2deg(offset):.2f} deg')
        success = self._comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_EstimationAddresses.SET_THETA_OFFSET,
            data=offset,
            input_type=ctypes.c_float,
            output_type=ctypes.c_bool
        )

        if not success:
            self.logger.error('Could not set theta offset')

        # self._comm.serial.executeFunction(
        #     module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
        #     address=addresses.TWIPR_ControlAddresses.ADDRESS_CONTROL_SET_MODE,
        #     data=mode.value,
        #     input_type=ctypes.c_uint8
        # )

    # ==================================================================================================================
    def _update(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def _onSample(self, sample: BILBO_LL_Sample, *args, **kwargs):
        self.state.v = sample.estimation.state.v
        self.state.theta = sample.estimation.state.theta
        self.state.theta_dot = sample.estimation.state.theta_dot
        self.state.psi = sample.estimation.state.psi
        self.state.psi_dot = sample.estimation.state.psi_dot

    # ------------------------------------------------------------------------------------------------------------------
    def _readState_LL(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
