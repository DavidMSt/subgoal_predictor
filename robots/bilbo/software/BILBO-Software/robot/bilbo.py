import ctypes
import os
import time

import math

# === OWN PACKAGES =====================================================================================================
from core.utils.delayed_executor import delayed_execution
from hardware.control_board import RobotControl_Board
from hardware.stm32.stm32 import resetSTM32
from robot.bilbo_common import BILBO_Common
from robot.core import MainProvider, set_main_provider
from robot.experiment.bilbo_experiment import BILBO_ExperimentHandler
from robot.interfaces.bilbo_interfaces import BILBO_Interfaces
from robot.utilities.bilbo_utilities import BILBO_Utilities
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import Event, event_definition, SubscriberListener
from core.utils.singletonlock.singletonlock import SingletonLock, terminate
from robot.communication.bilbo_communication import BILBO_Communication
from robot.control.bilbo_control_data import BILBO_Control_Mode
from robot.control.bilbo_control import BILBO_Control
from robot.drive.bilbo_drive import BILBO_Drive
from robot.estimation.bilbo_estimation import BILBO_Estimation
from robot.logging.bilbo_logging import BILBO_Logging
from robot.logging.bilbo_sample import BILBO_Sample_General
from robot.sensors.bilbo_sensors import BILBO_Sensors
from core.utils.logging_utils import Logger, setLoggerLevel
from robot.supervisor.twipr_supervisor import TWIPR_Supervisor
from core.utils.revisions import get_versions, is_ll_version_compatible
import robot.lowlevel.stm32_addresses as stm32_addresses
from core.utils.exit import register_exit_callback

# === GLOBAL VARIABLES =================================================================================================
setLoggerLevel('wifi', 'ERROR')
setLoggerLevel('Sound', 'ERROR')


# === Callbacks ========================================================================================================
@callback_definition
class BILBO_Callbacks:
    update: CallbackContainer


# === Events ===========================================================================================================
@event_definition
class BILBO_Events:
    update: Event


# ======================================================================================================================
class BILBO(MainProvider):
    id: str

    common: BILBO_Common
    board: RobotControl_Board

    communication: BILBO_Communication
    control: BILBO_Control
    estimation: BILBO_Estimation
    drive: BILBO_Drive
    sensors: BILBO_Sensors
    experiment_handler: BILBO_ExperimentHandler
    logging: BILBO_Logging
    utilities: BILBO_Utilities

    events: BILBO_Events

    supervisor: TWIPR_Supervisor
    lock: SingletonLock

    loop_time: float

    _initialized: bool = False
    _last_update_time: float = 0
    _first_sample_user_message_sent: bool = False
    _eventListener: SubscriberListener

    # === INIT =========================================================================================================
    def __init__(self, reset_stm32: bool = False):
        self.lock = SingletonLock(lock_file="/tmp/twipr.lock", timeout=10, override=True, override_timeout=5)
        self.lock.__enter__()

        self.logger = Logger("BILBO")

        # param = os.sched_param(80)  # priority 1–99 (higher = higher priority)
        # os.sched_setscheduler(0, os.SCHED_FIFO, param)

        if reset_stm32:
            self.logger.info(f"Reset STM32. This takes ~2 Seconds")
            resetSTM32()
            time.sleep(3)

        self.common = BILBO_Common()

        # Read the ID from the ID file
        self.id = self.common._get_id()

        self.loop_time = 0
        self.update_time = 0
        self._last_update_time = 0

        self._initialized = False

        set_main_provider(self)

        # Set up the control board
        self.board = RobotControl_Board()

        # Start the communication module (WI-FI, Serial and SPI)
        self.communication = BILBO_Communication(board=self.board, core=self.common)

        # Set up the individual modules
        self.control = BILBO_Control(core=self.common, comm=self.communication)
        self.estimation = BILBO_Estimation(common=self.common, comm=self.communication)
        self.drive = BILBO_Drive(comm=self.communication)
        self.sensors = BILBO_Sensors(comm=self.communication)
        self.supervisor = TWIPR_Supervisor(comm=self.communication)

        self.utilities = BILBO_Utilities(core=self.common, communication=self.communication, board=self.board)
        self.experiment_handler = BILBO_ExperimentHandler(common=self.common,
                                                          communication=self.communication,
                                                          utilities=self.utilities,
                                                          control=self.control, )

        self.logging = BILBO_Logging(common=self.common,
                                     communication=self.communication,
                                     control=self.control,
                                     estimation=self.estimation,
                                     drive=self.drive,
                                     sensors=self.sensors,
                                     experiment_handler=self.experiment_handler,
                                     )

        self.interfaces = BILBO_Interfaces(communication=self.communication,
                                           control=self.control,
                                           core=self.common)

        # Test Command
        self.communication.wifi.newCommand(identifier='test',
                                           function=self.test,
                                           arguments=['input'],
                                           description='Test the communication')

        self.events = BILBO_Events()
        self.callbacks = BILBO_Callbacks()

        register_exit_callback(self._shutdown, priority=0)
        register_exit_callback(self._shutdownInit, priority=2)

        self._startup_phase = True


        def on_new_timecode(timecode):
            self.board.status_led.toggle()

        self.common.timecode_listener.callbacks.new_timecode.register(on_new_timecode)

    # === METHODS ======================================================================================================
    def init(self):

        self.board.init()
        self.board.start()
        self.communication.init()
        self.communication.start()

        self.estimation.init()
        self.control.init()
        self.supervisor.init()
        self.sensors.init()
        self.logging.init()
        self.experiment_handler.init()



    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.logger.important(f"Start {self.id}")
        # self.communication.start()
        self.utilities.start()

        success = self.control.start()

        if not success:
            self.logger.error("Cannot write control configuration. Exit program")
            exit()

        self.supervisor.start()
        self.sensors.start()
        self.estimation.start()
        self.logging.start()

        self._last_update_time = time.perf_counter()
        time.sleep(0.05)
        if not self._resetLowLevel():
            self.logger.error("Failed to reset lowlevel firmware")
            raise Exception("Failed to reset lowlevel firmware")

        self.utilities.playTone('notification')
        self.utilities.speak(f'Start {self.id}')

        self.communication.startSampleListener()
        self._eventListener = self.communication.events.rx_stm32_sample.on(self.update, spawn_new_threads=False)
        self.interfaces.start()

        delayed_execution(lambda: setattr(self, '_startup_phase', False), 1)

        # self.board.setRGBLEDExtern([0, 0, 0])

    # ------------------------------------------------------------------------------------------------------------------
    def update(self, *args, **kwargs):
        """
        This is the main update function for the robot
        """
        # if not self._initialized:
        #     return
        time_loop_start = time.perf_counter()
        self.update_time = time.perf_counter() - self._last_update_time
        self._last_update_time = time.perf_counter()

        # Update the logging
        self.logging.update()

        # Update the experiment handler
        self.experiment_handler.step()

        # Update the control
        self.control.update()

        # self._setExternalLEDs()

        # Callbacks
        self.callbacks.update.call()

        # Events
        self.events.update.set()

        if not self._first_sample_user_message_sent:
            self._sendFirstSampleMessage()

        self.loop_time = time.perf_counter() - time_loop_start
        # print(f"Loop time {self.loop_time:.4f} s, Update time {self.update_time:.4f} s, Tick {self.tick}")

        if self.loop_time > 0.18:
            self.logger.warning(f"Loop took {self.loop_time * 1000:.2f} ms")

        if self.update_time > 0.2 and self._startup_phase == False:
            self.logger.warning(f"Update took {self.update_time * 1000:.2f} ms")

        self.common.end_of_step()
        
    # === PRIVATE METHODS ==============================================================================================
    def _resetLowLevel(self):
        # self.board.beep()

        return self.communication.serial.executeFunction(
            module=stm32_addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=stm32_addresses.TWIPR_GeneralAddresses.ADDRESS_FIRMWARE_RESET,
            input_type=None,
            output_type=ctypes.c_bool,
            timeout=1
        )

    def _shutdownInit(self):
        self.logger.important(f"Shutdown {self.id}")
        self.control.set_mode(BILBO_Control_Mode.OFF)
        self._eventListener.stop()
        self.utilities.playTone('warning')
        self.board.setRGBLEDExtern([2, 2, 2])

    # ------------------------------------------------------------------------------------------------------------------
    def _shutdown(self, *args, **kwargs):
        self.logger.info("Shutdown BILBO")
        time.sleep(1)
        self.lock.__exit__(None, None, None)

    # ------------------------------------------------------------------------------------------------------------------
    def _checkFirmwareRevision(self) -> bool:
        revision_stm32 = self.communication.serial.readFirmwareRevision()
        revision_data = get_versions()

        # Check if the LL firmware is compatible
        if revision_stm32 is None or not is_ll_version_compatible(current_ll_version=(revision_stm32['major'],
                                                                                      revision_stm32['minor']),
                                                                  min_ll_version=(
                                                                          revision_data['stm32_firmware']['major'],
                                                                          revision_data['stm32_firmware'][
                                                                              'minor'])):
            self.logger.error(
                f"STM32 Firmware not compatible. Current Version: {revision_stm32['major']}.{revision_stm32['minor']}."
                f" Required > {revision_data['stm32_firmware']['major']}.{revision_data['stm32_firmware']['minor']}")
            return False

        self.logger.info(
            f"Software Version {revision_data['software']['major']}.{revision_data['software']['minor']}"
            f" (STM32: {revision_stm32['major']}.{revision_stm32['minor']})")
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def getSample(self):
        raise NotImplementedError

    # ------------------------------------------------------------------------------------------------------------------
    def _setExternalLEDs(self):
        """
        Update the 16 external LEDs based on the control mode.

        - OFF: set all LEDs to a very dim white [2,2,2].
        - BALANCING:
            * Outer LEDs (1,8,9,16) solid green at MAX_GREEN.
            * Inner LEDs (3,4,5,6) on BOTH sides fade from MAX_GREEN at theta=0
              down to 0 at |theta| >= OFF_DEG (in degrees).
        """
        # knobs (can optionally be set on 'self' to override defaults)
        MAX_GREEN = getattr(self, "led_max_green", 20)  # 0..255, default 20
        OFF_DEG = getattr(self, "led_theta_off_deg", 1.0)  # degrees to fully off

        # Helper to push a uniform color to all 16 quickly
        def _all(c):
            self.board.setAllLEDsExtern([tuple(c)] * 16)

        mode = self.control.mode

        if mode == BILBO_Control_Mode.OFF:
            _all((2, 2, 2))
            return

        if mode == BILBO_Control_Mode.BALANCING:
            # Read theta in radians
            theta = float(self.logging.sample.lowlevel.estimation.state.theta)
            abs_theta = abs(theta)

            # Map |theta| in [0, OFF_RAD] -> fade in [1..0]
            off_rad = math.radians(OFF_DEG) if OFF_DEG > 0 else 0.0
            if off_rad <= 0.0:
                fade = 1.0
            else:
                fade = 1.0 - (abs_theta / off_rad)
                if fade < 0.0:
                    fade = 0.0
                elif fade > 1.0:
                    fade = 1.0

            inner_val = int(round(MAX_GREEN * fade))
            outer_val = int(MAX_GREEN)

            # Start with all off
            colors = [(0, 0, 0)] * 16

            # Outer LEDs: indices 1-based -> (1,8) on side A, (9,16) on side B
            for idx in (1, 8, 9, 16):
                colors[idx - 1] = (0, outer_val, 0)

            # Inner LEDs on each side: 3,4,5,6 (1-based)
            for base in (0, 8):  # side A = 0..7, side B = 8..15
                for i in (3, 4, 5, 6):
                    colors[base + (i - 1)] = (0, inner_val, 0)

            self.board.setAllLEDsExtern(colors)
            return

        # Fallback for other modes: turn everything off (adjust if you prefer)
        self.board.setAllLEDsExtern([(0, 0, 0)] * 16)

    # ------------------------------------------------------------------------------------------------------------------
    def _sendFirstSampleMessage(self):
        self.logger.info(f"BILBO is running!")
        # self.logger.info(f"Battery Voltage: {self.logging.sample.sensors.power.bat_voltage:.2f} V")
        self._first_sample_user_message_sent = True

    # ------------------------------------------------------------------------------------------------------------------
    def test(self, input):
        return input

    # ------------------------------------------------------------------------------------------------------------------
    def __del__(self):
        if hasattr(self, 'lock'):
            self.lock.__exit__(None, None, None)
