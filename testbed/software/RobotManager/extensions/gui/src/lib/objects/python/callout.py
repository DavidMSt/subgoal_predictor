from __future__ import annotations

import dataclasses
import enum
import uuid
from typing import Any

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.colors import mix_colors
from core.utils.logging_utils import Logger
from core.utils.time import delayed_execution
from extensions.gui.src.gui import AddMessage, AddMessageData, RemoveMessage, RemoveMessageData


# ----------------------------------------------------------------------------------------------------------------------
class CalloutType(enum.Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"
    DEBUG = "debug"


# ----------------------------------------------------------------------------------------------------------------------
class CalloutSymbols:
    INFO = "ℹ️"
    WARNING = "⚠️"
    ERROR = "❌"
    SUCCESS = "✅"
    DEBUG = "🤖"


# ----------------------------------------------------------------------------------------------------------------------
@callback_definition
class CalloutButton_Callbacks:
    clicked: CallbackContainer


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class CalloutButton:
    text: str
    text_color: str | list = 'white'
    color: str | list = "transparent"

    def __post_init__(self):
        self.callbacks = CalloutButton_Callbacks()


# ----------------------------------------------------------------------------------------------------------------------
class CalloutColors:
    INFO = [0.0, 0.482, 1.0]  # #007BFF
    WARNING = [1.0, 0.647, 0.0]  # #FFA500
    ERROR = [1.0, 0.0, 0.0]  # #FF0000
    SUCCESS = [0.0, 0.8, 0.0]  # #00CC00

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def get_rgb(type_: CalloutType) -> list[float]:
        return getattr(CalloutColors, type_.name, [0.8, 0.8, 0.8])  # fallback to gray

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def get_rgba(type_: CalloutType, alpha: float = 0.2) -> list[float]:
        return CalloutColors.get_rgb(type_) + [alpha]


# ----------------------------------------------------------------------------------------------------------------------
@callback_definition
class Callout_Callbacks:
    closed: CallbackContainer
    button: CallbackContainer


@dataclasses.dataclass
class CalloutPayload:
    id: str
    config: dict
    type: str = 'callout'


# ======================================================================================================================
class Callout:
    id: str
    text: str
    symbol: str
    timeout: int
    type: CalloutType
    buttons: list[CalloutButton]

    handler: CalloutHandler

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, content: str,
                 symbol: str | None = None,
                 timeout: int = None,
                 callout_type: CalloutType = CalloutType.INFO,
                 buttons: list[CalloutButton] = None,
                 **kwargs
                 ):

        self.id = str(uuid.uuid4())
        self.content = content
        self.symbol = symbol or self._get_symbol(callout_type)
        self.timeout = timeout
        self.type = callout_type

        self.buttons = buttons or []

        default_config = {
            'background_color': mix_colors(CalloutColors.get_rgba(self.type, 0.15), [0.5, 0.5, 0.5, 0.2], t=0.8),
            'border_color': CalloutColors.get_rgb(self.type),
            'border_width': 1,
            'text_color': [1, 1, 1],
            'title': None,
            'font_size': 9,  # pt
            'font_family': 'inherit',
        }

        self.config = {**default_config, **kwargs}

        self.logger = Logger(f"Callout({self.id})", "DEBUG")

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def uid(self):
        if self.handler is not None:
            return f"{self.handler.uid}/{self.id}"
        return self.id

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self.handler.remove(self.id)

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        config = {
            'id': self.uid,
            'content': self.content,
            'symbol': self.symbol,
            'timeout': self.timeout,
            'type': self.type.value,
            'buttons': [dataclasses.asdict(b) for b in self.buttons],
            **self.config
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> CalloutPayload:
        payload = CalloutPayload(
            id=self.id,
            config=self.getConfiguration(),
        )
        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def onEvent(self, message, sender=None) -> None:
        match message['event']:
            case 'close':
                self.close()
            case _:
                self.logger.warning(f"Callout received unknown message: {message}")

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _get_symbol(type_: CalloutType) -> str:
        if type_ == CalloutType.INFO:
            return CalloutSymbols.INFO
        elif type_ == CalloutType.WARNING:
            return CalloutSymbols.WARNING
        elif type_ == CalloutType.ERROR:
            return CalloutSymbols.ERROR
        elif type_ == CalloutType.SUCCESS:
            return CalloutSymbols.SUCCESS
        elif type_ == CalloutType.DEBUG:
            return CalloutSymbols.DEBUG
        else:
            raise ValueError(f"Unknown callout type: {type_}")


# ======================================================================================================================
@callback_definition
class CalloutHandler_Callbacks:
    send_message: CallbackContainer


class CalloutHandler:
    callouts: dict[str, Callout]

    def __init__(self, gui):
        self.callouts = {}
        self.callbacks = CalloutHandler_Callbacks()
        self.logger = Logger("CalloutHandler", "DEBUG")

        self.gui = gui

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def uid(self):
        if self.gui is not None:
            return f"{self.gui.uid}/callouts"
        return "callouts"

    # ------------------------------------------------------------------------------------------------------------------
    def add(self, callout: Callout = None, **kwargs):
        if callout is None:
            callout = Callout(**kwargs)

        callout.handler = self
        self.callouts[callout.id] = callout

        message = AddMessage(
            data=AddMessageData(
                type='callout',
                parent=self.gui.uid,
                id=callout.uid,
                config=callout.getPayload(),
            )
        )

        self.callbacks.send_message.call(message)

        if (callout.timeout is not None) and (callout.timeout > 0):
            delayed_execution(self.remove, callout.timeout, callout.id)

        return callout

    # ------------------------------------------------------------------------------------------------------------------
    def remove(self, callout_id: str):
        if callout_id in self.callouts:
            callout = self.callouts[callout_id]

            message = RemoveMessage(
                RemoveMessageData(
                    type='callout',
                    id=callout.uid,
                    parent=self.gui.uid,
                )
            )
            self.callbacks.send_message.call(message)
            del self.callouts[callout_id]
            self.logger.info(f"Callout {callout_id} removed.")

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> None:
        self.logger.info(f"CalloutHandler received message: {message}")

    # ------------------------------------------------------------------------------------------------------------------
    def getCallout(self, callout_id: str) -> Callout | None:
        return self.callouts.get(callout_id)
