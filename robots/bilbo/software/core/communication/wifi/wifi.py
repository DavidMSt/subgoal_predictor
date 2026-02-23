import dataclasses
import queue
from typing import Union

from core.communication.wifi.protocol import JSON_Message
from core.communication.wifi.udp.protocols.udp_json_protocol import UDP_JSON_Message
from core.communication.wifi.udp.udp import UDP
from core.settings import UDP_PORT_ADDRESS_STREAM
from core.utils import network
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.dataclass_utils import from_dict, asdict_optimized
from core.utils.events import event_definition, Event
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.websockets import WebsocketClient


# === UTILS ============================================================================================================

# === WIFI DEVICE ======================================================================================================
@dataclasses.dataclass
class DeviceInformation:
    device_class: str = ''
    device_type: str = ''
    device_name: str = ''
    device_id: str = ''
    address: str = ''
    revision: int = 0


@callback_definition
class WIFI_Device_Callbacks:
    connected: CallbackContainer
    disconnected: CallbackContainer
    message: CallbackContainer


@event_definition
class WIFI_Device_Events:
    connected: Event
    disconnected: Event
    message: Event


class WIFI_Device:
    callbacks: WIFI_Device_Callbacks
    events: WIFI_Device_Events

    information: DeviceInformation

    rx_queue: queue.Queue
    use_rx_queue: bool = True

    connected: bool = False

    _udp_socket: UDP
    _websocket_client: WebsocketClient

    _exit: bool = False

    # === INIT =============================================================================================================
    def __init__(self, information: DeviceInformation, address=None):

        self.information = information

        # Get the local IP address. TODO: Add a loop here if not connected
        if address is None:
            address = network.getLocalIP_RPi()

        self.address = address
        self.callbacks = WIFI_Device_Callbacks()
        self.events = WIFI_Device_Events()

        # Logger
        self.logger = Logger('WIFI Device', 'DEBUG')

        # Message queue
        self.rx_queue = queue.Queue()

        # UDP Socket listening for server data broadcasts
        self._udp_socket = UDP(address=self.address, port=UDP_PORT_ADDRESS_STREAM)
        self._udp_socket.callbacks.rx.register(self._udpRx_callback)

        # Websocket client for connecting to server
        self._websocket_client = WebsocketClient()
        self._websocket_client.events.connected.on(self._connected_event)
        self._websocket_client.events.disconnected.on(self._disconnected_event)
        self._websocket_client.callbacks.message.register(self._message_callback)

        # Register exit handler
        register_exit_callback(self.close)

    # === PROPERTIES ===================================================================================================
    @property
    def server_address(self):
        return self._websocket_client.address

    @property
    def server_port(self):
        return self._websocket_client.port

    # === METHODS ======================================================================================================
    def init(self):
        self._udp_socket.init()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.logger.info(f"Starting WIFI on {self.address}")
        self._udp_socket.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self._udp_socket.close()
        self._websocket_client.close()
        self.connected = False

    # ------------------------------------------------------------------------------------------------------------------
    def send(self, message: Union[JSON_Message, dict]):
        if isinstance(message, JSON_Message):
            message = asdict_optimized(message)

        self._websocket_client.send(message)

    # === PRIVATE METHODS ==================================================================================================
    def _connect(self):

        # 1. Pause the udp listener
        self._udp_socket.callbacks.rx.remove(self._udpRx_callback)

        # 2. Connect to the websocket
        self._websocket_client.connect()

        # 3. Check in 5 seconds if the websocket is connected
        success = self._websocket_client.events.connected.wait(timeout=5)

        # 4. If not connected, resume the udp listener
        if not success:
            self._udp_socket.callbacks.rx.register(self._udpRx_callback)
            return False
        else:
            return True

    # ------------------------------------------------------------------------------------------------------------------
    def _sendHandshakeMessage(self):
        handshake_message = JSON_Message()
        handshake_message.type = 'event'
        handshake_message.event = 'handshake'
        handshake_message.data = asdict_optimized(self.information)
        self.send(handshake_message)

    # ------------------------------------------------------------------------------------------------------------------
    def _udpRx_callback(self, message: UDP_JSON_Message, *args, **kwargs):
        try:
            address = message.data.get('address')
            port = message.data.get('port')

            if address is None or port is None:
                self.logger.error("Invalid UDP server broadcast message")
                return

            if not self.connected:
                self._websocket_client.address = address
                self._websocket_client.port = port
                self._connect()
        except Exception as e:
            self.logger.error(f"Error in UDP RX callback: {e}")

    # ----------------------------------------------------------------------------------------------------------------------
    def _connected_event(self, *args, **kwargs):
        self.logger.info("Connected to server. Sending Handshake")
        self._sendHandshakeMessage()
        self.callbacks.connected.call()
        self.events.connected.set()

    # ----------------------------------------------------------------------------------------------------------------------
    def _disconnected_event(self, *args, **kwargs):
        self.logger.warning("Disconnected from server")
        self.callbacks.disconnected.call()
        self.events.disconnected.set()

    # ----------------------------------------------------------------------------------------------------------------------
    def _message_callback(self, message: dict, *args, **kwargs):
        try:
            tcp_message = from_dict(JSON_Message, message)
        except Exception as e:
            self.logger.error(f"Error in message decoding: {e}")
            return
        if self.use_rx_queue:
            self.rx_queue.put_nowait(tcp_message)

        self.callbacks.message.call(tcp_message)
        self.events.message.set(tcp_message)
    # ----------------------------------------------------------------------------------------------------------------------
