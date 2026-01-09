from __future__ import annotations

import abc
import dataclasses
import math
import os
import threading
import uuid
from dataclasses import is_dataclass
from typing import Any

import numpy as np

# === CUSTOM MODULES ===================================================================================================
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.dataclass_utils import asdict_optimized
from core.utils.dict import update_dict
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.time import IntervalTimer
from core.utils.websockets import WebsocketServer
from extensions.gui.src.lib.objects.objects import Widget
from extensions.gui.src.lib.utilities import split_path

babylon_path = os.path.join(os.path.dirname(__file__), "babylon_lib")


# === BABYLON OBJECT ===================================================================================================
@callback_definition
class BabylonObjectCallbacks:
    update: CallbackContainer


# ----------------------------------------------------------------------------------------------------------------------
class BabylonObject(abc.ABC):
    """
    Base class for Babylon visualization objects.
    """

    parent: BabylonObjectGroup | BabylonVisualization | None = None

    type: str = None
    id: str = None

    pollable: bool = True

    config: dict = None
    data: Any | None = None

    # === INIT =========================================================================================================
    def __init__(self, object_id: str, **kwargs):
        """
        Initialize a BabylonObject.
        """

        default_config = {
            'name': '',
            'visible': True,
            'dim': False,
            'highlight': False,
        }

        self.config = update_dict(default_config, kwargs, allow_add=False)
        if self.config['name'] == '':
            self.config['name'] = object_id

        self.id = object_id
        self.object_type = None  # To be defined in subclasses.
        self.data = None

        self.callbacks = BabylonObjectCallbacks()

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def uid(self):
        if self.parent is None:
            return self.id
        else:
            return f"{self.parent.uid}/{self.id}"

    # === METHODS ======================================================================================================
    def getBabylon(self) -> BabylonVisualization | None:
        if isinstance(self.parent, BabylonVisualization):
            return self.parent
        elif isinstance(self.parent, BabylonObjectGroup):
            return self.parent.getBabylon()
        else:
            return None

    # ------------------------------------------------------------------------------------------------------------------
    def update(self):
        babylon = self.getBabylon()
        if babylon is None:
            return

        if isinstance(babylon, BabylonVisualization):
            babylon.updateObject(
                object=self,
                data=self.getData()
            )

    # ------------------------------------------------------------------------------------------------------------------
    def updateConfig(self):

        babylon = self.getBabylon()

        if babylon is None:
            return

        if isinstance(babylon, BabylonVisualization):
            babylon.updateObjectConfig(
                object_id=self.uid,
                config=self.getConfig()
            )

    # ------------------------------------------------------------------------------------------------------------------
    def function(self, function_name, **kwargs):

        babylon = self.getBabylon()
        if babylon is None:
            return

        if isinstance(babylon, BabylonVisualization):
            babylon.objectFunction(
                object_id=self.uid,
                function_name=function_name,
                arguments=kwargs
            )

    # ------------------------------------------------------------------------------------------------------------------
    def setConfig(self, key, value):
        self.config[key] = value
        self.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    @abc.abstractmethod
    def getConfig(self) -> dict:
        """
        Serialize the object into a message dictionary for the web app.
        """
        ...

    # ------------------------------------------------------------------------------------------------------------------
    @abc.abstractmethod
    def getData(self) -> dict:
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def send(self, message, client=None):
        babylon = self.getBabylon()

        if babylon is not None:
            babylon.send(message, client)

    # ------------------------------------------------------------------------------------------------------------------
    def update_from_data(self, data: dict):
        """
        Update object parameters from a data dictionary.
        """
        self.data.update(data)
        self.callbacks.update.call(self)

    # ------------------------------------------------------------------------------------------------------------------
    def on_remove(self):
        """
        Cleanup actions when the object is removed.
        """
        pass

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self):
        payload = {
            'type': self.type,
            'id': self.uid,
            'config': self.getConfig(),
            'data': self.getData()
        }
        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def visible(self, visible: bool):
        self.setConfig('visible', visible)

    # ------------------------------------------------------------------------------------------------------------------
    def dim(self, dim: bool):
        self.setConfig('dim', dim)

    # ------------------------------------------------------------------------------------------------------------------
    def highlight(self, highlight: bool):
        self.setConfig('highlight', highlight)


# ======================================================================================================================
class BabylonObjectGroup:
    object_id: str
    objects: dict[str, BabylonObject | BabylonObjectGroup]

    parent: BabylonObjectGroup | BabylonVisualization | None = None

    config: dict

    # === INIT =========================================================================================================
    def __init__(self, object_id: str = None, **kwargs):

        if object_id is None:
            object_id = f"group_{str(uuid.uuid4())}"

        self.object_id = object_id

        default_config = {

        }

        self.config = update_dict(default_config, kwargs)
        self.data = {}
        self.objects = {}
        self.logger = Logger(f'Object Group {self.object_id}')

    # === PROPERTIES ===================================================================================================
    @property
    def uid(self):
        if self.parent is None:
            return self.object_id
        else:
            return f"{self.parent.uid}/{self.object_id}"

    # === METHODS ======================================================================================================
    def getBabylon(self) -> BabylonVisualization | None:
        if isinstance(self.parent, BabylonVisualization):
            return self.parent
        elif isinstance(self.parent, BabylonObjectGroup):
            return self.parent.getBabylon()
        else:
            return None

    # ------------------------------------------------------------------------------------------------------------------
    def addObject(self, object: BabylonObject | BabylonObjectGroup) -> BabylonObject | BabylonObjectGroup | None:
        if object.parent is not None:
            self.logger.warning(f"Object {object.object_id} already has a parent.")
            return None

        if object.object_id in self.objects:
            self.logger.warning(f"Object {object.object_id} already exists in group {self.object_id}.")
            return None

        object.parent = self
        self.objects[object.object_id] = object

        message = {
            'type': 'addObject',
            'id': object.uid,
            'object_type': object.object_type,
            'payload': object.getPayload()
        }

        self.getBabylon().broadcast(message)

        return object

    # ------------------------------------------------------------------------------------------------------------------
    def removeObject(self, object: BabylonObject | BabylonObjectGroup | str) -> None:

        if isinstance(object, str):
            if object not in self.objects:
                self.logger.warning(f"Object {object} not found in group {self.object_id}.")
                return
            object = self.objects[object]

        if not isinstance(object, BabylonObject | BabylonObjectGroup):
            self.logger.warning(f"Object {object} is not a BabylonObject or BabylonObjectGroup.")
            return

        message = {
            'type': 'removeObject',
            'id': object.uid
        }

        self.objects.pop(object.object_id)
        object.parent = None
        object.on_remove()

        self.getBabylon().broadcast(message)

    # ------------------------------------------------------------------------------------------------------------------
    def getObjectByPath(self, path) -> BabylonObject | BabylonObjectGroup | None:

        # 1) normalize slashes
        trimmed = path.strip("/")

        # 2) Split the path
        object_id, remainder = split_path(trimmed)

        if not object_id or object_id not in self.objects:
            self.logger.warning(f"Object with id {object_id} not found in group {self.object_id}.")
            return None

        if not remainder:
            return self.objects[object_id]
        else:
            if isinstance(self.objects[object_id], BabylonObjectGroup):
                return self.objects[object_id].getObjectByPath(remainder)
            else:
                self.logger.warning(
                    f"Object with id {object_id} is not a BabylonObjectGroup but remainder is not empty")
                return None

        return None

    # ------------------------------------------------------------------------------------------------------------------
    def getConfig(self) -> dict:
        config = {
            **self.config
        }

        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getData(self) -> dict:
        data = {
            **self.data,
        }
        return data

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> dict:
        payload = {
            'id': self.uid,
            'type': 'group',
            'config': self.getConfig(),
            'objects': {k: v.getPayload() for k, v in self.objects.items()},
            'data': self.getData(),
        }

        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def visible(self, visible: bool):
        for obj in self.objects.values():
            obj.visible(visible)

    # ------------------------------------------------------------------------------------------------------------------
    def dim(self, dim: bool):
        for obj in self.objects.values():
            obj.dim(dim)

    # ------------------------------------------------------------------------------------------------------------------
    def highlight(self, highlight: bool):
        for obj in self.objects.values():
            obj.highlight(highlight)


# ======================================================================================================================
@callback_definition
class BabylonCallbacks:
    new_client: CallbackContainer
    client_disconnected: CallbackContainer
    client_loaded: CallbackContainer
    object_event: CallbackContainer


# ======================================================================================================================
@dataclasses.dataclass
class Babylon_UpdateMessage:
    updates: dict[str, dict | list[dict]] = dataclasses.field(default_factory=dict)
    type: str = 'update'


# ======================================================================================================================
class BabylonVisualization:
    """
    Manages the BabylonJS visualization web application.
    """

    objects: dict[str, BabylonObject]

    config: dict
    server: WebsocketServer

    _clients: list
    _update_message: Babylon_UpdateMessage
    _update_message_lock = threading.Lock()

    _poll_objects: bool = True

    _exit: bool = False
    Ts: float = 0.05

    # === INIT =========================================================================================================
    def __init__(self,
                 id: str,
                 host='localhost',
                 port=9000,
                 babylon_config=None):

        babylon_default_config = {
            "title": "ABCDEF",
            "websocket_host": "localhost",
            "websocket_port": "9000",
            "coordinate_system_length": 0.5,
            "show_coordinate_system": True,

            "background_color": [31 / 255, 32 / 255, 35 / 255],
            "ambient_color": [0.5, 0.5, 0.5],

            "scene": {
                "add_fog": True,
                "fog_color": [31 / 255, 32 / 255, 35 / 255],
                "fog_density": 0.08,
                "fog_mode": "exp2",
            },

            "camera": {
                "position": [2, -2, 1],
                "target": [0, 0, 0],
                "alpha": math.radians(-18),
                "beta": math.radians(70),
                "radius": 3.5,
                "fov": math.radians(65),
                "radius_lower_limit": 0.5,
                "radius_upper_limit": 6,
            },

            "lights": {
                "hemispheric_direction": [2, -1, 0],
            },

            "ui": {
                "text_color": [1, 1, 1],
                "font_size": 40,
            },
        }
        self.config = update_dict(babylon_default_config, babylon_config)

        self.id = id

        self.callbacks = BabylonCallbacks()
        self.logger = Logger('BABYLON', 'INFO')

        self.server = WebsocketServer(host=host, port=port, heartbeats=False)
        self.server.callbacks.new_client.register(self._new_client_callback)
        self.server.callbacks.client_disconnected.register(self._client_disconnected_callback)
        self.server.callbacks.message.register(self._client_message_callback)

        self.objects = {}
        self._clients = []

        self.update_message = Babylon_UpdateMessage()

        self.timer = IntervalTimer(self.Ts, raise_race_condition_error=False)

        register_exit_callback(self.close)

        self._thread = None

    # ------------------------------------------------------------------------------------------------------------------
    def init(self):
        """
        Initialize the web app visualization.
        (Any additional initialization code can be added here.)
        """
        pass

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        """
        Start the visualization in a separate thread.
        """
        self.logger.info("Starting Babylon visualization")

        self.server.start()

        self._thread = threading.Thread(target=self._task, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self._exit = True

        if hasattr(self, '_thread') and self._thread is not None and self._thread.is_alive():
            self._thread.join()

        self.server.stop()
        self.logger.important(f"Babylon visualization stopped")

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def uid(self):
        return self.id

    # ------------------------------------------------------------------------------------------------------------------
    def getObjectByUID(self, uid):

        # 1) drop any leading slash
        trimmed = uid.lstrip("/")

        # 2) Split off the GUI ID
        babylon_id, remainder = split_path(trimmed)

        if not babylon_id or babylon_id != self.id:
            self.logger.warning(f"UID '{uid}' does not match this Babylon's ID '{self.id}'")
            return None

        if not remainder:
            return self

        object_id, remainder = split_path(remainder)

        if object_id not in self.objects:
            self.logger.warning(f"Object with id {object_id} not found in scene.")
            return None

        if not remainder:
            return self.objects[object_id]
        else:
            if isinstance(self.objects[object_id], BabylonObjectGroup):
                return self.objects[object_id].getObjectByPath(remainder)
            else:
                self.logger.warning(
                    f"Object with id {object_id} is not a BabylonObjectGroup but remainder is not empty")
                return None

        return None

    # ------------------------------------------------------------------------------------------------------------------
    def _task(self):

        self.timer.reset()
        while not self._exit:
            if self._poll_objects:
                self._pollObjects()
            self._sendUpdate()
            self.timer.sleep_until_next()

    # ------------------------------------------------------------------------------------------------------------------
    def addObject(self, obj: BabylonObject):
        """
        Add a BabylonObject instance to the scene.
        """

        if obj.id in self.objects:
            raise ValueError(f"Object with id {obj.id} already exists.")

        self.objects[obj.id] = obj

        # Set the visualization reference so the object can send updates automatically.
        obj.parent = self

        payload = obj.getPayload()

        message = {
            'type': 'addObject',
            'id': obj.uid,
            'object_type': obj.object_type,
            'payload': payload
        }

        self.send(message)

    # ------------------------------------------------------------------------------------------------------------------
    def removeObject(self, object: Widget | BabylonObject | str):
        """
        Remove an object from the scene by its ID.
        """

        if isinstance(object, str):
            if object not in self.objects:
                self.logger.warning(f"Object {object} not found in scene.")
                return
            object = self.objects[object]

        message = {
            'type': 'removeObject',
            'id': object.uid
        }

        self.objects[object.id].on_remove()
        del self.objects[object.id]

        self.send(message)
        self.logger.info(f"Object {object.uid} removed from scene.")

    # ------------------------------------------------------------------------------------------------------------------
    def updateObjectConfig(self, object_id, config):
        """
        Update the configuration of an object in the scene.
        """
        message = {
            'type': 'updateObjectConfig',
            'id': object_id,
            'config': config
        }

        self.send(message)

    # ------------------------------------------------------------------------------------------------------------------
    def updateObject(self, object: BabylonObject | BabylonObjectGroup, data):
        with self._update_message_lock:
            self.update_message.updates[object.uid] = data

    # ------------------------------------------------------------------------------------------------------------------
    def objectFunction(self, object_id, function_name, arguments: dict):
        """
        Call a function on an object in the scene.
        """
        message = {
            'type': 'objectFunction',
            'id': object_id,
            'function': function_name,
            'arguments': arguments
        }

        self.send(message)

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self):
        payload = {
            'config': self.config,
            'objects': {k: v.getPayload() for k, v in self.objects.items()},
        }

        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def broadcast(self, message):

        if is_dataclass(message):
            message = asdict_optimized(message)

        self.send(message)

    # ------------------------------------------------------------------------------------------------------------------
    def send(self, message, client=None):

        if is_dataclass(message):
            message = asdict_optimized(message)

        if client:
            self.server.sendToClient(client, message)
        else:
            self.server.send(message)

    # ------------------------------------------------------------------------------------------------------------------
    def onEvent(self, event_message, sender):
        self.logger.important(f"Received event message: {event_message} from {sender}")

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------

    # === PRIVATE METHODS ==============================================================================================
    def _pollObjects(self):
        for id, obj in self.objects.items():
            if obj.pollable:
                data = obj.getData()
                self.updateObject(obj, data)

    # ------------------------------------------------------------------------------------------------------------------
    def _sendUpdate(self):
        with self._update_message_lock:
            if len(self.update_message.updates) == 0:
                return

            update_message_dict = asdict_optimized(self.update_message)
            self.update_message = Babylon_UpdateMessage()
            self.send(update_message_dict)

    # ------------------------------------------------------------------------------------------------------------------
    def _initializeClient(self, client):
        self.logger.important(f"Initializing client: {client}")

        message = {
            'type': 'init',
            'payload': self.getPayload()
        }
        self.send(message, client)

    # ------------------------------------------------------------------------------------------------------------------
    def _onMessage(self, message, sender=None):
        self.logger.debug(f"Received message: {message}")

        if 'type' not in message:
            self.logger.warning(f"Message does not contain a type: {message}")
            return

        match message['type']:
            case 'loaded':
                ...
            case 'event':
                self._handleEventMessage(message, sender)
            case _:
                self.logger.warning(f"Unknown message type: {message['type']}")

    # ------------------------------------------------------------------------------------------------------------------
    def _new_client_callback(self, client):
        self.logger.debug(f"New client connected: {client}")

        if client not in self._clients:
            self._clients.append(client)
            self.callbacks.new_client.call(client)
            self._initializeClient(client)
        else:
            self.logger.warning(f"Client already connected: {client}")

    # ------------------------------------------------------------------------------------------------------------------
    def _client_disconnected_callback(self, client, *args, **kwargs):

        if client in self._clients:
            self._clients.remove(client)
            self.callbacks.client_disconnected.call(client)
            self.logger.debug(f"Client disconnected: {client}")
        else:
            self.logger.warning(f"Client not found: {client}")

    # ------------------------------------------------------------------------------------------------------------------
    def _client_message_callback(self, client, message):
        self._onMessage(message, client)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleEventMessage(self, message, sender=None):
        if 'id' not in message:
            self.logger.warning(f"Event message does not contain an id: {message}")
            return

        object = self.getObjectByUID(message['id'])

        if object is None:
            self.logger.warning(f"Object with id {message['id']} not found.")

        object.onEvent(message, sender)
