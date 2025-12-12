# === CUSTOM MODULES ===================================================================================================
import dataclasses
import queue
import threading
import time
from typing import Any

from core.communication.protocol import JSON_Message
from core.communication.wifi.udp.protocols.udp_json_protocol import UDP_JSON_Message
from core.communication.wifi.udp.udp import UDP_Broadcast, UDP
from core.archive.settings import UDP_PORT_ADDRESS_STREAM, WS_SERVER_PORT
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.dataclass_utils import asdict_optimized, from_dict
from core.utils.events import event_definition, Event, EventFlag
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.time import precise_sleep
from core.utils.websockets import WebsocketServer, WebsocketServerClient

# ======================================================================================================================
DEBUG = False


# === REQUESTS =========================================================================================================
class Request:
    event: Event
    id: int

    def __init__(self):
        self.event = Event()


# === DEVICE ===========================================================================================================
@dataclasses.dataclass
class DeviceInformation:
    device_class: str = ''
    device_type: str = ''
    device_name: str = ''
    device_id: str = ''
    address: str = ''
    revision: int = 0


# --- CALLBACKS ---
@callback_definition
class DeviceCallbacks:
    registered: CallbackContainer
    disconnected: CallbackContainer
    rx: CallbackContainer
    stream: CallbackContainer
    event: CallbackContainer
    timeout: CallbackContainer


# --- EVENTS ---
@event_definition
class DeviceEvents:
    rx: Event
    stream: Event
    event: Event = Event(flags=EventFlag('event', str))
    timeout: Event


class Device:
    client: WebsocketServerClient
    information: DeviceInformation

    message_thread: threading.Thread

    _readRequests: dict[int, Request]

    _exit: bool = False

    # === INIT =========================================================================================================
    def __init__(self, client: WebsocketServerClient, information: DeviceInformation):
        self.client = client

        self.client.callbacks.disconnected.register(self._clientDisconnectedCallback)

        self.information = information

        self.callbacks = DeviceCallbacks()
        self.events = DeviceEvents()

        self._readRequests = {}

        self.logger = Logger(f"Device {self.information.device_id}")

        self.message_thread = threading.Thread(target=self._messageTask, daemon=True)
        self.message_thread.start()

        self._sendSyncMessage()

    # === PROPERTIES ===================================================================================================
    @property
    def address(self):
        return self.client.address

    # === METHODS ======================================================================================================
    def close(self):
        self._exit = True

    # ------------------------------------------------------------------------------------------------------------------
    def writeValue(self, value_name, value, request_response: bool = False, timeout: float = 0.1):
        message = JSON_Message()
        message.type = 'write'
        message.address = ''
        message.source = ''
        message.request_response = request_response

        if isinstance(value_name, str):
            params = value_name.split('/')

            if len(params) == 1:
                message.data = {
                    value_name: value
                }
            elif len(params) == 2:
                message.data = {
                    params[0]: {
                        params[1]: value
                    }
                }
            else:
                raise Exception("Levels >1 are not allowed for parameters")

        elif isinstance(value_name, dict):
            message.data = value_name

        request = None
        if request_response:
            request = self._addRequest(message_id=message.id)

        self._send(message=message)

        if request_response and request is not None:
            if request.event.wait(timeout=timeout):
                self._readRequests.pop(request.id)
                data = request.event.get_data()
                success = data['success']
                return success
            else:
                self._readRequests.pop(request.id)
                return Exception("Timeout")
        else:
            return True

    # ------------------------------------------------------------------------------------------------------------------
    def readValue(self, value_name, timeout: float = 0.1):
        message = JSON_Message()
        message.type = 'read'
        message.address = ''
        message.source = ''
        message.request_response = True
        message.data = {
            'value_name': value_name
        }

        request = self._addRequest(message_id=message.id)
        self._send(message=message)
        if request.event.wait(timeout=timeout):
            self._readRequests.pop(request.id)
            data = request.event.get_data()
            success = data['success']
            if success:
                return data['output']
            else:
                raise Exception(f"Cannot read value {value_name}")
        else:
            self._readRequests.pop(request.id)
            raise TimeoutError

    # ------------------------------------------------------------------------------------------------------------------
    def executeFunction(self,
                        function_name,
                        arguments,
                        return_type: type = None,
                        request_response: bool = False,
                        timeout: float = 1):

        message = JSON_Message()
        message.type = 'function'
        message.address = ''
        message.source = ''
        message.request_response = request_response

        message.data = {
            'function_name': function_name,
            'arguments': arguments
        }

        if DEBUG:
            response_timer = time.perf_counter()

        if request_response:
            request = self._addRequest(message_id=message.id)
            message.request_id = request.id
        else:
            request = None

        self._send(message=message)

        if request is not None:
            if request.event.wait(timeout=timeout, stale_event_time=0.1):
                if DEBUG:
                    response_time = (time.perf_counter() - response_timer) * 1000  # noqa
                    self.logger.debug(
                        f"Got response for function \"{function_name}\"! Response time: {response_time:.0f} ms")

                data = request.event.get_data()
                success = data.get('success', None)
                self._readRequests.pop(request.id)

                if return_type is None:
                    return success
                else:
                    if success:
                        return data['output']
                    else:
                        return None
            else:
                self._readRequests.pop(request.id)
                self.logger.error(f"Timeout for function request \"{function_name}\" ({request.id})")
                raise TimeoutError
        else:
            return True

    # ------------------------------------------------------------------------------------------------------------------
    def sendEvent(self, event: str, data: Any, request_response: bool = False, timeout: float = 1) -> bool:
        message = JSON_Message()
        message.type = 'event'
        message.address = ''
        message.source = ''
        message.request_response = request_response
        message.event = event

        message.data = data

        request = None
        if request_response:
            request = self._addRequest(message_id=message.id)

        self._send(message=message)

        if request is not None:
            if request.event.wait(timeout=timeout, stale_event_time=0.1):
                self._readRequests.pop(request.id)
                return True
            else:
                self._readRequests.pop(request.id)
                raise TimeoutError
        return True

    # === PRIVATE METHODS ==============================================================================================
    def _messageTask(self):
        while not self._exit:
            message = self.client.rx_queue.get()
            self._rxMessageCallback(message)
            precise_sleep(0.001)

    # ------------------------------------------------------------------------------------------------------------------
    def _send(self, message: JSON_Message):
        if self.client.connected:
            self.client.send(asdict_optimized(message))
        else:
            ...
            # self.logger.warning(f"Cannot send message to {self.address}: Client not connected. Message {message}")

    # ------------------------------------------------------------------------------------------------------------------
    def _rxMessageCallback(self, message: dict, *args, **kwargs) -> None:

        # Parse into a TCP JSON Message
        tcp_message = from_dict(JSON_Message, message)

        match tcp_message.type:
            case 'response':
                self._handleResponseMessage(tcp_message)
            case 'event':
                self._handleEventMessage(tcp_message)
            case 'stream':
                self._handleStreamMessage(tcp_message)
            case _:
                self.logger.warning(f"Unknown message type: {tcp_message.type}")
                return

        self.callbacks.rx.call(tcp_message)
        self.events.rx.set(data=tcp_message)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleResponseMessage(self, message: JSON_Message):
        if message.request_id in self._readRequests:
            read_request = self._readRequests[message.request_id]
            read_request.event.set(data=message.data)
        else:
            self.logger.warning(f"Got a response for an unknown request: {message.request_id}")

    # ------------------------------------------------------------------------------------------------------------------
    def _handleEventMessage(self, message: JSON_Message):
        self.callbacks.event.call(message)
        self.events.event.set(data=message, flags={'event': message.event})

    # ------------------------------------------------------------------------------------------------------------------
    def _handleStreamMessage(self, message: JSON_Message):
        self.callbacks.stream.call(message)
        self.events.stream.set(data=message)

    # ------------------------------------------------------------------------------------------------------------------
    def _addRequest(self, message_id) -> Request:
        read_request = Request()
        read_request.id = message_id
        self._readRequests[read_request.id] = read_request
        return read_request

    # ------------------------------------------------------------------------------------------------------------------
    def _sendSyncMessage(self):
        self.sendEvent('sync', {'server_time': time.time()})

    # ------------------------------------------------------------------------------------------------------------------
    def _clientDisconnectedCallback(self):
        self.callbacks.disconnected.call(self)

    # ------------------------------------------------------------------------------------------------------------------


# === DEVICE SERVER ====================================================================================================
@callback_definition
class DeviceServerCallbacks:
    new_device: CallbackContainer
    device_disconnected: CallbackContainer
    # stream: CallbackContainer


@event_definition
class DeviceServerEvents:
    new_device: Event = Event(copy_data_on_set=False, flags=EventFlag('type', str))
    device_disconnected: Event = Event(copy_data_on_set=False, flags=EventFlag('type', str))
    # stream: Event = Event(flags=[EventFlag('type', str), EventFlag('device_id', str)])


class DeviceServer:
    websocket_server: WebsocketServer
    udp_socket: UDP

    callbacks: DeviceServerCallbacks
    events: DeviceServerEvents

    clients: list[WebsocketServerClient]

    devices: dict[str, Device]

    # === INIT =========================================================================================================
    def __init__(self, host, port=WS_SERVER_PORT, udp_port=UDP_PORT_ADDRESS_STREAM):
        self.host = host
        self.port = port
        self.udp_port = udp_port

        self.callbacks = DeviceServerCallbacks()
        self.events = DeviceServerEvents()

        # Create the UDP Socket
        self.udp_socket = UDP(host, udp_port)
        self._setupUdpBroadcast()

        # Create the WebSocket Server
        self.websocket_server = WebsocketServer(host, port)
        self.websocket_server.callbacks.new_client.register(self._clientConnectedCallback)
        self.websocket_server.callbacks.client_disconnected.register(self._clientDisconnectedCallback)

        self.clients = []

        # Devices
        self.devices = {}

        # Misc
        self.logger = Logger('DeviceServer', 'DEBUG')

        # Exit Handler
        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.logger.info("Starting Device Server")
        self.udp_socket.start()
        self.websocket_server.start()
        pass

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self.logger.info("Closing Device Server")
        self.websocket_server.stop()
        self.udp_socket.close()

    # === PRIVATE METHODS ==============================================================================================
    def _setupUdpBroadcast(self):
        broadcast_message = UDP_JSON_Message()
        broadcast_message.type = None
        broadcast_message.data = {
            'address': self.host,
            'port': self.port
        }

        udp_broadcast = UDP_Broadcast()
        udp_broadcast.message = broadcast_message
        udp_broadcast.time = 1

        self.udp_socket.addBroadcast(udp_broadcast)

    # ------------------------------------------------------------------------------------------------------------------
    def _clientConnectedCallback(self, client: WebsocketServerClient):
        if client in self.clients:
            self.logger.warning(f"Client {client.address} already connected")
            return
        self.clients.append(client)
        self.logger.info(f"New client connected: {client.address}")
        client.callbacks.message.register(self._clientMessageCallback)

    # ------------------------------------------------------------------------------------------------------------------
    def _clientDisconnectedCallback(self, client):
        if client not in self.clients:
            self.logger.warning(f"Client {client.address} not found")
            return
        self.clients.remove(client)
        self.logger.info(f"Client disconnected: {client.address}")

    # ------------------------------------------------------------------------------------------------------------------
    def _clientMessageCallback(self, message: dict, client: WebsocketServerClient):
        try:
            tcp_message = from_dict(JSON_Message, message)
        except Exception as e:
            self.logger.error(f"Error parsing message: {e}")
            return

        if tcp_message.type == 'event' and tcp_message.event == 'handshake':
            try:
                device_information = from_dict(DeviceInformation, tcp_message.data)
            except Exception as e:
                self.logger.error(f"Error in device handshake: {e}")
                return

            # Check if this device is already registered
            if device_information.device_id in self.devices:
                self.logger.warning(f"Device with ID {device_information.device_id} already registered")
                return

            new_device = Device(client, device_information)
            self.devices[device_information.device_id] = new_device
            self.callbacks.new_device.call(new_device)
            self.events.new_device.set(data=new_device, flags={'type': device_information.device_type})
            new_device.callbacks.disconnected.register(self._deviceDisconnected_callback)

            # new_device.callbacks.stream.register(self._deviceStream_callback)

            # Remove the callback
            client.callbacks.message.remove(self._clientMessageCallback)

            self.logger.info(f"New device registered: {device_information.device_id}")

    # ------------------------------------------------------------------------------------------------------------------
    def _deviceDisconnected_callback(self, device):
        self.devices.pop(device.information.device_id)
        self.callbacks.device_disconnected.call(device)
        self.events.device_disconnected.set(data=device, flags={'type': device.information.device_type})

    # # ------------------------------------------------------------------------------------------------------------------
    # def _deviceStream_callback(self, stream, device):
    #     self.callbacks.stream.call(stream, device)
    #     self.events.stream.set(data=stream, flags={'type': stream.type, 'device_id': device.information.device_id})
