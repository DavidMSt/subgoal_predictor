# === OWN PACKAGES =====================================================================================================
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.exit import register_exit_callback
from hardware.control_board import RobotControl_Board
from robot.bilbo_common import BILBO_Common
from robot.communication.serial.bilbo_comm_serial import BILBO_Serial_Communication
from robot.communication.spi.bilbo_comm_spi import BILBO_SPI_Interface
from robot.communication.wifi.bilbo_wifi import BILBO_WIFI_Interface
from core.utils.events import Event, event_definition
from core.utils.logging_utils import Logger, enable_redirection, setLoggerLevel, disable_redirection
from robot.lowlevel.stm32_sample import BILBO_LL_Sample

# ======================================================================================================================
handler = None

logger = Logger("COMMUNICATION")
logger.setLevel("INFO")


# ======================================================================================================================
@callback_definition
class BILBO_Communication_Callbacks:
    rx_stm32_sample: CallbackContainer


# ======================================================================================================================
@event_definition
class BILBO_Communication_Events:
    rx_stm32_sample: Event = Event(data_type=BILBO_LL_Sample, copy_data_on_set=False)
    stm32_tick: Event


# ======================================================================================================================
class BILBO_Communication:
    board: RobotControl_Board

    serial: BILBO_Serial_Communication
    wifi: BILBO_WIFI_Interface
    spi: BILBO_SPI_Interface

    events: BILBO_Communication_Events
    callbacks: BILBO_Communication_Callbacks

    def __init__(self, board: RobotControl_Board, core: BILBO_Common):
        self.board = board
        self.core = core

        self.wifi = BILBO_WIFI_Interface(core=self.core)

        self.serial = BILBO_Serial_Communication(interface=self.board.serial_interface)
        self.spi = BILBO_SPI_Interface(interface=self.board.spi_interface,
                                       sample_notification_pin=self.board.board_config.definitions.pins.new_samples_interrupt.pin)

        self.callbacks = BILBO_Communication_Callbacks()
        self.events = BILBO_Communication_Events()

        # Configure the SPI Interface
        self.spi.callbacks.rx_latest_sample.register(self._stm32_rx_sample_callback)

        setLoggerLevel('tcp', 'WARNING')
        self.wifi.callbacks.connected.register(self._wifi_connected_callback)
        self.wifi.callbacks.disconnected.register(self._wifi_disconnected_callback)

        self.wifi.newCommand(identifier='test',
                        function=self.test,
                        arguments=['input'],
                        description='Test the communication')

        register_exit_callback(self.close)
        # Configure Logging Redirect
        enable_redirection(self._log_redirection)

    # === METHODS ======================================================================================================
    def init(self):
        self.spi.init()
        self.serial.init()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.spi.start()
        self.serial.start()
        self.wifi.start()

        global handler
        handler = self

    # ------------------------------------------------------------------------------------------------------------------
    def startSampleListener(self):
        self.spi.startSampleListener()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        disable_redirection(self._log_redirection)
        logger.info("Closing BILBO Communication")
        self.spi.close()

    # ------------------------------------------------------------------------------------------------------------------
    def test(self, input):
        return input

    # === PRIVATE METHODS ==============================================================================================
    def _stm32_rx_sample_callback(self, sample, *args, **kwargs):
        # sample = samples[0]

        # Execute the callbacks
        for callback in self.callbacks.rx_stm32_sample:
            callback(sample)

        # Set the events
        self.events.rx_stm32_sample.set(sample)
        self.events.stm32_tick.set(sample.tick)

    # ------------------------------------------------------------------------------------------------------------------
    def _log_redirection(self, log_entry, log, logger: Logger, level):
        self.wifi.sendEvent(event='log',
                            data={
                                'level': level,
                                'message': log,
                                'logger': logger.name
                            })

    # ------------------------------------------------------------------------------------------------------------------
    def _wifi_connected_callback(self, *args, **kwargs):
        logger.info("Connected to Server")

    # ------------------------------------------------------------------------------------------------------------------
    def _wifi_disconnected_callback(self, *args, **kwargs):
        logger.warning("Disconnected from Server")
