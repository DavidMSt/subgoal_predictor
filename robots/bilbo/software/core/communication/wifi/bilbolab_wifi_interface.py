import dataclasses
import sys
import threading
import time
import types as _types
import typing
from typing import Union, Callable, Any, get_origin, get_args

from core.communication.wifi.data_link import Command, CommandArgument, generateCommandDict
from core.communication.wifi.protocol import JSON_Message
from core.communication.wifi.wifi import WIFI_Device, DeviceInformation
from core.utils import network
from core.utils.callbacks import callback_definition, CallbackContainer, Callback
from core.utils.events import event_definition, Event
from core.utils.logging_utils import Logger
from core.utils.time import precise_sleep


# === WIFI EVENT DATA ==================================================================================================
@dataclasses.dataclass
class WifiEventData:
    """Structured payload sent over the wire for every WifiEvent."""
    event: str  # event id (e.g. 'path_finished')
    event_uid: str  # full uid (e.g. 'position_control:path_finished')
    container: str | None  # container id if given (e.g. 'position_control')
    flags: dict  # flag values
    data: Any  # actual event data


# === WIFI EVENT FLAG ==================================================================================================
class WifiEventFlag:
    """
    Flag definition for WifiEvent, mirroring EventFlag.

    Flags are sent alongside event data and can be used on the host
    to filter/route events (e.g. group='position_control').
    """
    id: str
    types: tuple[type, ...]

    def __init__(self, id: str, data_type: type | tuple[type, ...]):
        self.id = id
        if isinstance(data_type, tuple):
            if not data_type or not all(isinstance(t, type) for t in data_type):
                raise TypeError("data_type tuple must be non-empty and contain only types.")
            self.types = data_type
        elif isinstance(data_type, type):
            self.types = (data_type,)
        else:
            raise TypeError("data_type must be a type or tuple[type, ...]")

    def accepts(self, value: Any) -> bool:
        return isinstance(value, self.types)

    def describe(self) -> str:
        return " | ".join(t.__name__ for t in self.types)


# === WIFI EVENT =======================================================================================================
class WifiEvent:
    """
    A single outbound WiFi event, mirroring Event.

    Each WifiEvent has an id, an optional data_type (can be a dataclass),
    and optional flags (WifiEventFlag) for host-side filtering.

    Usage:
        @wifi_event_definition
        class ControlWifiEvents(WifiEventContainer):
            path_finished: WifiEvent = WifiEvent(data_type=dict, flags=WifiEventFlag('group', str))
            mode_changed: WifiEvent

        container = ControlWifiEvents(wifi=self.communication.wifi)
        container.path_finished.send(data={'x': 3}, flags={'group': 'position_control'})
    """
    id: str | None
    data_type: type | None
    flags: dict[str, WifiEventFlag]

    parent: 'WifiEventContainer | None'
    _wifi: 'BILBOLab_Wifi_Interface | None'

    def __init__(self,
                 id: str = None,
                 data_type: type | None = None,
                 flags: WifiEventFlag | list[WifiEventFlag] = None):
        self.id = id
        self.data_type = data_type
        self.parent = None
        self._wifi = None

        if flags is None:
            flags = []
        if not isinstance(flags, list):
            flags = [flags]

        self.flags = {}
        for flag in flags:
            if flag.id in self.flags:
                raise ValueError(f"Duplicate flag id '{flag.id}'")
            self.flags[flag.id] = flag

    @property
    def uid(self) -> str:
        if self.parent is None or self.parent.id is None:
            return self.id
        return f"{self.parent.id}:{self.id}"

    def send(self, data: Any = None, flags: dict = None) -> None:
        if self._wifi is None:
            raise RuntimeError(f"WifiEvent '{self.id}' is not connected to a WiFi interface.")

        # Validate flags
        flags = flags or {}
        for flag_id, value in flags.items():
            if flag_id not in self.flags:
                raise ValueError(f"Unknown flag '{flag_id}' for WifiEvent '{self.id}'")
            if not self.flags[flag_id].accepts(value):
                ef = self.flags[flag_id]
                raise TypeError(
                    f"Flag '{flag_id}' expects {ef.describe()}, got {type(value).__name__}"
                )

        # Validate data type
        if data is not None and self.data_type is not None:
            if not isinstance(data, self.data_type):
                raise TypeError(
                    f"WifiEvent '{self.id}' expects data of type {self.data_type.__name__}, "
                    f"got {type(data).__name__}."
                )

        # Serialize dataclass data to dict
        if data is not None and dataclasses.is_dataclass(data) and not isinstance(data, type):
            data = dataclasses.asdict(data)

        # Build structured event payload
        container_id = self.parent.id if self.parent is not None else None
        event_data = WifiEventData(
            event=self.id,
            event_uid=self.uid,
            container=container_id,
            flags=flags,
            data=data,
        )

        self._wifi.sendEvent(event=self.uid, data=dataclasses.asdict(event_data))

    def __repr__(self):
        return f"<WifiEvent {self.uid}>"


# === WIFI EVENT CONTAINER =============================================================================================
class WifiEventContainer:
    """
    Container for WifiEvent instances, mirroring EventContainer.

    Tracks registered events by id. When events from a container are
    registered on the BILBOLab_Wifi_Interface, duplicate IDs are rejected.
    """
    id: str | None
    wifi_events: dict[str, WifiEvent]

    def __init__(self, wifi: 'BILBOLab_Wifi_Interface', id: str = None):
        self.id = id
        self._wifi = wifi
        self.wifi_events = {}

    def add_event(self, event: WifiEvent):
        if event.id in self.wifi_events:
            raise ValueError(f"WifiEvent '{event.id}' already exists in container '{self.id}'.")
        if event.parent is not None:
            raise ValueError(f"WifiEvent '{event.id}' already has a parent.")
        self.wifi_events[event.id] = event
        event.parent = self
        event._wifi = self._wifi

        # Register on the interface (checks global uniqueness)
        self._wifi.registerWifiEvent(event)


# === WIFI EVENT DEFINITION DECORATOR =================================================================================
def wifi_event_definition(cls):
    """
    Per-instance WifiEvent fields, mirroring @event_definition.

    Usage:
        @wifi_event_definition
        class PositionControlWifiEvents(WifiEventContainer):
            path_finished: WifiEvent = WifiEvent(data_type=dict, flags=WifiEventFlag('group', str))
            path_started: WifiEvent
            mode_changed: WifiEvent = WifiEvent(flags=WifiEventFlag('group', str))
    """
    original_init = getattr(cls, '__init__', None)

    # Resolve annotations (supports `from __future__ import annotations`)
    try:
        module_globals = sys.modules[cls.__module__].__dict__
        hints = typing.get_type_hints(cls, globalns=module_globals, localns=dict(vars(cls)))
    except Exception:
        hints = getattr(cls, '__annotations__', {}) or {}

    def _is_wifi_event_type(t) -> bool:
        if t is WifiEvent:
            return True
        if isinstance(t, str):
            return t == 'WifiEvent' or t.endswith('.WifiEvent')
        origin = get_origin(t)
        try:
            is_union = (origin is typing.Union) or (origin is _types.UnionType)
        except Exception:
            is_union = (origin is typing.Union)
        if is_union:
            return any(_is_wifi_event_type(arg) for arg in get_args(t))
        if origin is typing.ClassVar:
            return False
        return False

    def _clone_wifi_event(template: WifiEvent, new_id: str) -> WifiEvent:
        flags = [WifiEventFlag(ef.id, ef.types) for ef in template.flags.values()]
        return WifiEvent(id=new_id, data_type=template.data_type, flags=flags)

    def _ensure_container_bits(self):
        if not hasattr(self, 'wifi_events') or not isinstance(getattr(self, 'wifi_events'), dict):
            self.wifi_events = {}

        if not hasattr(self, 'add_event') or not callable(getattr(self, 'add_event')):
            def _add_event(_self, event: WifiEvent):
                if event.id in _self.wifi_events:
                    raise ValueError(f"WifiEvent '{event.id}' already exists in container.")
                if event.parent is not None:
                    raise ValueError(f"WifiEvent '{event.id}' already has a parent.")
                _self.wifi_events[event.id] = event
                event.parent = _self
                event._wifi = _self._wifi
                _self._wifi.registerWifiEvent(event)

            setattr(self, 'add_event', _add_event.__get__(self, self.__class__))

    def new_init(self, *args, **kwargs):
        if original_init:
            original_init(self, *args, **kwargs)

        _ensure_container_bits(self)

        # Process annotated attributes
        if isinstance(hints, dict):
            for attr_name, anno in hints.items():
                default_val = getattr(cls, attr_name, None)

                if isinstance(default_val, WifiEvent):
                    ev = _clone_wifi_event(default_val, new_id=attr_name)
                    setattr(self, attr_name, ev)
                    self.add_event(ev)
                    continue

                if _is_wifi_event_type(anno) and attr_name not in self.__dict__:
                    ev = WifiEvent(id=attr_name)
                    setattr(self, attr_name, ev)
                    self.add_event(ev)

        # Pick up unannotated class-level WifiEvent defaults
        for attr_name, value in vars(cls).items():
            if isinstance(value, WifiEvent) and attr_name not in self.__dict__:
                ev = _clone_wifi_event(value, new_id=attr_name)
                setattr(self, attr_name, ev)
                self.add_event(ev)

    cls.__init__ = new_init
    return cls


# === BILBOLAB WIFI INTERFACE ==========================================================================================
@callback_definition
class BILBOLab_Wifi_Interface_Callbacks:
    connected: CallbackContainer
    disconnected: CallbackContainer


@event_definition
class BILBOLab_Wifi_Interface_Events:
    connected: Event
    disconnected: Event


class BILBOLab_Wifi_Interface:
    device: WIFI_Device

    callbacks: BILBOLab_Wifi_Interface_Callbacks
    events: BILBOLab_Wifi_Interface_Events

    commands: dict[str, Command]
    _wifi_events: dict[str, WifiEvent]

    connected: bool = False
    _server_time_offset: float = None

    _task: threading.Thread
    _exit: bool = False

    # === INIT =========================================================================================================
    def __init__(self, information: DeviceInformation, address: str = None):

        self.callbacks = BILBOLab_Wifi_Interface_Callbacks()
        self.events = BILBOLab_Wifi_Interface_Events()

        if address is None:
            address = network.getLocalIP_RPi()

        self.address = address

        # Logger
        self.logger = Logger("BILBOLab_Wifi_Interface", "DEBUG")

        # Wi-Fi Device
        self.device = WIFI_Device(information, address=self.address)
        self.device.events.connected.on(self._deviceConnected_event)
        self.device.events.disconnected.on(self._deviceDisconnected_event)

        # Commands
        self.commands = {}

        # WiFi event registry
        self._wifi_events = {}

        # Thread
        self._task = threading.Thread(target=self._taskFunction, daemon=True)

    # === METHODS ======================================================================================================
    def init(self) -> None:
        self.device.init()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self) -> None:
        self.logger.info(f"Starting WIFI Interface")
        self._task.start()
        self.device.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):

        self._exit = True
        if self._task is not None and self._task.is_alive():
            self._task.join()
        self.device.close()

    # ------------------------------------------------------------------------------------------------------------------
    def sendEvent(self, event: str, data: dict = None, request_id: int = 0) -> None:
        if data is None:
            data = {}

        message = JSON_Message()
        message.source = self.device.information.device_id
        message.address = ''
        message.type = 'event'
        message.event = event
        message.data = data
        message.request_id = request_id
        self._send(message)

    # ------------------------------------------------------------------------------------------------------------------
    def registerWifiEvent(self, event: WifiEvent) -> None:
        """Register a WifiEvent on this interface. Rejects duplicate UIDs."""
        uid = event.uid
        if uid in self._wifi_events:
            raise ValueError(
                f"WifiEvent '{uid}' is already registered on this interface."
            )
        self._wifi_events[uid] = event
        event._wifi = self

    # ------------------------------------------------------------------------------------------------------------------
    def sendStream(self, data: dict = None, stream_id: str = None) -> None:
        if data is None:
            data = {}

        message = JSON_Message()
        message.source = self.device.information.device_id
        message.address = ''
        message.type = 'stream'
        message.data = {
            'stream_id': stream_id,
            'data': data,
        }
        self._send(message)

    # ------------------------------------------------------------------------------------------------------------------
    def addCommand(self, command: Command) -> None:
        if command.identifier in self.commands:
            self.logger.warning(f"Command with identifier '{command.identifier}' already exists.")
            return
        self.commands[command.identifier] = command

    # ------------------------------------------------------------------------------------------------------------------
    def newCommand(self, identifier: str,
                   function: Union[Callable, Callback],
                   arguments: list[CommandArgument],
                   description: str = "",
                   execute_in_thread: bool = True) -> Command:

        command = Command(identifier, function, arguments, description, execute_in_thread)
        self.addCommand(command)
        return command

    # ------------------------------------------------------------------------------------------------------------------
    def generateCommandOverview(self) -> dict:
        return generateCommandDict(self.commands)

    # ------------------------------------------------------------------------------------------------------------------
    def getSynchronizedTime(self) -> Union[float, None]:
        if self._server_time_offset is None:
            return None
        return time.time() + self._server_time_offset

    # === PRIVATE METHODS ==============================================================================================
    def _taskFunction(self):
        while not self._exit:
            message = self.device.rx_queue.get()
            self._handleMessage(message)
            precise_sleep(0.001)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleMessage(self, message: JSON_Message):

        if message.type == 'write':
            self._handleWriteMessage(message)
        elif message.type == 'read':
            self._handleReadMessage(message)
        elif message.type == 'event':
            self._handleEventMessage(message)
        elif message.type == 'function':
            self._handleFunctionMessage(message)
        else:
            self.logger.warning(f"Received message with unknown type '{message.type}'")

    # ------------------------------------------------------------------------------------------------------------------
    def _handleWriteMessage(self, message):
        raise NotImplementedError('Write messages are currently not supported')
        # errors = {}
        #
        # for entry, value in message.data.items():
        #     if entry not in self.data:
        #         logger.warning(f"Received parameter {entry}, which is not a valid entry.")
        #         errors[entry] = "Invalid parameter"
        #         continue
        #
        #     param = self.data[entry]
        #     # Handle single parameter.
        #     if isinstance(param, DataLink):
        #         try:
        #             if not param.set(value):
        #                 errors[entry] = f"Failed to set parameter {entry}"
        #                 logger.warning(f"Failed to set parameter {entry} to value {value}.")
        #             else:
        #                 logger.debug(f"Set parameter {entry} to value {value}.")
        #         except Exception as e:
        #             errors[entry] = str(e)
        #             logger.error(f"Exception setting parameter {entry}: {e}")
        #     # Handle group of parameters (only one level supported).
        #     elif isinstance(param, dict) and isinstance(value, dict):
        #         for sub_entry, sub_value in value.items():
        #             if sub_entry not in param:
        #                 logger.warning(f"Received parameter {entry}:{sub_entry}, which is not a valid entry.")
        #                 errors[f"{entry}:{sub_entry}"] = "Invalid sub-parameter"
        #                 continue
        #             sub_param = param[sub_entry]
        #             if not isinstance(sub_param, DataLink):
        #                 logger.warning(f"Cannot set parameter {entry}:{sub_entry}: unsupported parameter structure.")
        #                 errors[f"{entry}:{sub_entry}"] = "Invalid parameter structure"
        #                 continue
        #             try:
        #                 if not sub_param.set(sub_value):
        #                     logger.warning(f"Failed to set parameter {entry}:{sub_entry} to value {sub_value}.")
        #                     errors[f"{entry}:{sub_entry}"] = f"Failed to set parameter {sub_entry}"
        #                 else:
        #                     logger.debug(f"Set parameter {entry}:{sub_entry} to value {sub_value}.")
        #             except Exception as e:
        #                 errors[f"{entry}:{sub_entry}"] = str(e)
        #                 logger.error(f"Exception setting parameter {entry}:{sub_entry}: {e}")
        #     else:
        #         logger.warning(f"Parameter {entry} has unsupported structure.")
        #         errors[entry] = "Unsupported parameter structure"
        #
        # if message.request_response:
        #     response_msg = TCP_JSON_Message()
        #     response_msg.source = self.id
        #     response_msg.address = ''
        #     response_msg.type = 'response'
        #     response_msg.request_id = message.id
        #     response_msg.data = {"success": len(errors) == 0, "errors": errors}
        #     self._wifi_send(response_msg)
        # elif errors:
        #     # If no response is explicitly requested, send an event for the errors.
        #     self.sendEventMessage("write_error", {"errors": errors}, request_id=message.id)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleReadMessage(self, message):
        raise NotImplementedError('Read messages are currently not supported')
        # response = {}
        # errors = {}
        #
        # # If no specific parameter is requested, read all parameters.
        # if not message.data:
        #     for key, param in self.data.items():
        #         if isinstance(param, DataLink):
        #             try:
        #                 response[key] = param.get()
        #             except Exception as e:
        #                 errors[key] = str(e)
        #                 logger.error(f"Error reading parameter {key}: {e}")
        #         elif isinstance(param, dict):
        #             response[key] = {}
        #             for subkey, sub_param in param.items():
        #                 if isinstance(sub_param, DataLink):
        #                     try:
        #                         response[key][subkey] = sub_param.get()
        #                     except Exception as e:
        #                         errors[f"{key}:{subkey}"] = str(e)
        #                         logger.error(f"Error reading parameter {key}:{subkey}: {e}")
        #                 else:
        #                     errors[f"{key}:{subkey}"] = "Invalid parameter structure"
        #         else:
        #             errors[key] = "Unsupported parameter structure"
        # else:
        #     # Determine keys to read based on the type of message.data.
        #     if isinstance(message.data, dict):
        #         keys_to_read = message.data.keys()
        #     elif isinstance(message.data, list):
        #         keys_to_read = message.data
        #     else:
        #         keys_to_read = [message.data]
        #
        #     for key in keys_to_read:
        #         if key not in self.data:
        #             errors[key] = "Invalid parameter"
        #             logger.warning(f"Received read request for invalid parameter {key}.")
        #             continue
        #         param = self.data[key]
        #         if isinstance(param, DataLink):
        #             try:
        #                 response[key] = param.get()
        #             except Exception as e:
        #                 errors[key] = str(e)
        #                 logger.error(f"Error reading parameter {key}: {e}")
        #         elif isinstance(param, dict):
        #             response[key] = {}
        #             subkeys = None
        #             # If message.data is a dict and provides a list of subkeys, use it; otherwise, read all subkeys.
        #             if isinstance(message.data, dict) and isinstance(message.data.get(key, None), list):
        #                 subkeys = message.data[key]
        #             if subkeys is None:
        #                 for subkey, sub_param in param.items():
        #                     if isinstance(sub_param, DataLink):
        #                         try:
        #                             response[key][subkey] = sub_param.get()
        #                         except Exception as e:
        #                             errors[f"{key}:{subkey}"] = str(e)
        #                             logger.error(f"Error reading parameter {key}:{subkey}: {e}")
        #                     else:
        #                         errors[f"{key}:{subkey}"] = "Invalid parameter structure"
        #             else:
        #                 for subkey in subkeys:
        #                     if subkey not in param:
        #                         errors[f"{key}:{subkey}"] = "Invalid sub-parameter"
        #                         logger.warning(f"Received read request for invalid sub-parameter {key}:{subkey}.")
        #                         continue
        #                     sub_param = param[subkey]
        #                     if isinstance(sub_param, DataLink):
        #                         try:
        #                             response[key][subkey] = sub_param.get()
        #                         except Exception as e:
        #                             errors[f"{key}:{subkey}"] = str(e)
        #                             logger.error(f"Error reading parameter {key}:{subkey}: {e}")
        #                     else:
        #                         errors[f"{key}:{subkey}"] = "Invalid parameter structure"
        #         else:
        #             errors[key] = "Unsupported parameter structure"
        #             logger.warning(f"Parameter {key} has unsupported structure.")
        #
        # response_msg = TCP_JSON_Message()
        # response_msg.source = self.id
        # response_msg.address = ''
        # response_msg.type = 'response'
        # response_msg.request_id = message.id
        # response_msg.data = {"output": response, "errors": errors, "success": len(errors) == 0}
        # self._wifi_send(response_msg)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleEventMessage(self, message):

        if message.event == 'sync':
            server_time = message.data.get('server_time', None)
            if server_time is not None:
                self._server_time_offset = server_time - time.time()
            else:
                self.logger.warning("Received sync event without server time")

    # ------------------------------------------------------------------------------------------------------------------
    def _handleFunctionMessage(self, message):

        if 'function_name' not in message.data:
            self.logger.warning("Received function message without function name")
            return

        function_name = message.data['function_name']

        if function_name not in self.commands:
            self.logger.warning(f"Received function {function_name}, which is not a valid entry.")
            self.sendEvent("function_error", {"success": False, "error": f"Function {function_name} not found"},
                           request_id=message.id)
            return

        if 'arguments' not in message.data:
            self.logger.warning(f"Received function {function_name} without arguments")
            self.sendEvent("function_error", {"success": False, "error": f"Missing input for function {function_name}"},
                           request_id=message.id)
            return

        arguments = message.data['arguments']

        def execute_function():
            output = None
            error = None
            try:
                output = self.commands[function_name].execute(arguments)
                success = True
            except Exception as e:
                self.logger.warning(f"Error executing function {function_name}: {e}")
                success = False
                error = str(e)

            if message.request_response is not None and message.request_response:
                response_message = JSON_Message()
                response_message.address = ''
                response_message.source = self.device.information.device_id
                response_message.type = 'response'
                response_message.request_id = message.request_id
                response_message.data = {'output': output,
                                         'error': error,
                                         'success': success}
                # print(f"Sending response for function {function_name}: {response_message.request_id}")
                self._send(response_message)

        if self.commands[function_name].execute_in_thread:
            thread = threading.Thread(target=execute_function, daemon=True)
            thread.start()
        else:
            execute_function()

    # ------------------------------------------------------------------------------------------------------------------
    def _send(self, message: JSON_Message):
        self.device.send(message)

    # ------------------------------------------------------------------------------------------------------------------
    def _sendDeviceData(self):

        device_data = {
            'information': self.device.information,
            'commands': self.generateCommandOverview(),
        }

        self.sendEvent('interface_information', device_data)

    # ------------------------------------------------------------------------------------------------------------------
    def _deviceConnected_event(self, *args, **kwargs):
        self.connected = True
        self.logger.info(f"Interface connected to server")
        self._sendDeviceData()
        self.callbacks.connected.call()
        self.events.connected.set()

    # ------------------------------------------------------------------------------------------------------------------
    def _deviceDisconnected_event(self, *args, **kwargs):
        self.connected = False
        self.logger.warning(f"Interface disconnected from server")
        self.callbacks.disconnected.call()
        self.events.disconnected.set()
