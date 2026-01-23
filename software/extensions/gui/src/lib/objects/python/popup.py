from __future__ import annotations

import dataclasses
from typing import Any

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import Event, event_definition
from core.utils.logging_utils import Logger
from core.utils.websockets import WebsocketServerClient
from extensions.gui.src.lib.objects.objects import Widget_Group
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.utilities import split_path


# ======================================================================================================================
class PopupInstance:
    popup: Popup
    client: WebsocketServerClient

    def __init__(self, popup: Popup, client: WebsocketServerClient):
        self.popup = popup
        self.client = client


# ======================================================================================================================
@dataclasses.dataclass
class PopupPayload:
    id: str
    group: dict
    config: dict
    type: str = 'popup'


# ======================================================================================================================
@callback_definition
class Popup_Callbacks:
    closed: CallbackContainer
    message_send: CallbackContainer


@event_definition
class Popup_Events:
    closed: Event


# ======================================================================================================================
class Popup:
    id: str
    config: dict
    group: Widget_Group

    instances: list[PopupInstance]
    parent: Any

    allow_multiple: bool = False  # Whether multiple popups can be opened at the same time

    # === INIT =========================================================================================================
    def __init__(self, popup_id: str = None,
                 allow_multiple: bool = False,
                 instantiate_on_open: bool = True,
                 group_config: dict = None,
                 **kwargs,):

        self.id = popup_id or 'popup_' + str(id(self))

        default_config = {
            'background_color': 'transparent',
            'text_color': 'white',
            'resizable': True,
            'size': [400, 300],
            'grid': [5, 5],
            'grid_fit': 'fit',  # 'fit', 'horizontal', 'vertical'
            'title': '',
            'type': 'window',  # 'window', 'dialog'
            'closeable': True,  # Whether the popup can be closed
        }

        self.config = {**default_config, **kwargs}

        self.parent = None

        self.group = Widget_Group(
            group_id=f"{self.id}_group",
            rows=self.config['grid'][0],
            columns=self.config['grid'][1],
            background_color=self.config['background_color'],
            fit=True,
            **(group_config if group_config else {}),
        )

        self.group.parent = self

        self.logger = Logger(self.id)
        self.callbacks = Popup_Callbacks()
        self.events = Popup_Events()

        self.instances = []

    # ------------------------------------------------------------------------------------------------------------------
    def getGUI(self):
        if self.parent:
            return self.parent.getGUI()
        return None

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def uid(self):
        uid = self.id
        if self.parent is not None:
            uid = f"{self.parent.uid}/popups/{uid}"
        return uid

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        """Get the configuration of the popup."""
        config = {
            'id': self.uid,
            **self.config
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> PopupPayload:
        """Get the payload of the popup."""
        payload = PopupPayload(
            id=self.id,
            group=self.group.getPayload(),
            config=self.getConfiguration(),
        )
        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, client=None):

        remove_msg = {
            'type': 'remove',
            'data': {
                'type': 'popup',
                'parent': self.parent.uid,
                'id': self.uid,
            }
        }

        self.callbacks.message_send.call(remove_msg)
        self.callbacks.closed.call()

    # ------------------------------------------------------------------------------------------------------------------
    def onEvent(self, message, sender=None):
        if 'event' not in message:
            self.logger.warning(f"Message {message} has no event type")
            return

        self.handleEvent(message, sender)

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None):
        match message['event']:
            case 'closed':
                self.logger.info(f"Popup {self.id} closed manually")
                if self.config.get('closeable', True):
                    self.close()
            case _:
                self.logger.info(f"Popup {self.id} received an unknown event")

    # ------------------------------------------------------------------------------------------------------------------
    def getObjectByPath(self, path: str):
        """
        Given a path within this page (e.g. "button1" or
        "group1/subobj2"), find the direct child whose .id
        matches the first segment, and either return it or
        recurse into it if it’s a GUI_Object_Group.
        """
        # 1) normalize slashes
        trimmed = path.strip("/")

        # 3) split first id vs. remainder
        first_segment, remainder = split_path(trimmed)
        if not first_segment:
            return None

        if first_segment == self.group.id:
            if not remainder:
                return self.group
            else:
                # must be a group to descend further
                return self.group.getObjectByPath(remainder)

        return None


# ======================================================================================================================
@callback_definition
class YesNoPopup_Callbacks:
    yes: CallbackContainer
    no: CallbackContainer


class YesNoPopup(Popup):
    def __init__(self, title: str = 'YesNo', message: str = ''):
        config = {
            'title': title,
            'type': 'dialog',
            'closeable': False,
            'grid': [4, 4],
        }

        group_config = {
            'fill_empty': False,
        }

        super().__init__(popup_id='yesno', group_config=group_config, **config)

        self.yes_button = Button(
            widget_id='yes_button',
            text='Yes',
            color=[0.2, 0.5, 0.2],
        )
        self.no_button = Button(
            widget_id='no_button',
            text='No',
            color=[0.5, 0.2, 0.2],
        )

        self.group.addWidget(self.yes_button, width=1, height=1, row=4, column=2)
        self.group.addWidget(self.no_button, width=1, height=1, row=4, column=3)

        self.yes_button.callbacks.click.register(self._yesButtonClicked)
        self.no_button.callbacks.click.register(self._noButtonClicked)

    def _yesButtonClicked(self, *args, **kwargs):
        self.logger.info(f"Yes button clicked")
        self.close()

    def _noButtonClicked(self, *args, **kwargs):
        self.logger.info(f"No button clicked")
        self.close()
