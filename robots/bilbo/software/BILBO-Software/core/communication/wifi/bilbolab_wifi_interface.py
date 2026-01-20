import threading
import time
from typing import Union, Callable

from core.communication.wifi.data_link import Command, CommandArgument, generateCommandDict
from core.communication.wifi.protocol import JSON_Message
from core.communication.wifi.wifi import WIFI_Device, DeviceInformation
from core.utils import network
from core.utils.callbacks import callback_definition, CallbackContainer, Callback
from core.utils.events import event_definition, Event
from core.utils.logging_utils import Logger
from core.utils.time import precise_sleep


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