import abc
import dataclasses
import uuid
from typing import Any

from core.utils.logging_utils import Logger
from extensions.gui.src.lib.objects.python.popup import Popup
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.utilities import split_path


class ApplicationButton(Button):
    parent: Any = None

    @property
    def uid(self):
        if self.parent is not None:
            return f"{self.parent.uid}/{self.id}"
        else:
            return f"{self.id}"


# ======================================================================================================================
@dataclasses.dataclass
class Application_Payload:
    id: str
    config: dict
    type: str = 'application'


# ======================================================================================================================
class GUI_Popup_Application(abc.ABC):
    id: str
    popup: Popup | None
    button: Button

    gui = None

    # === INIT =========================================================================================================
    def __init__(self, id: str, name=None, config: dict = None, **kwargs):
        self.id = f"{id}_{str(uuid.uuid4())}"
        self.logger = Logger(f"Application {id}", 'DEBUG')
        self.popup = None
        self.button = ApplicationButton(f"{id}_button", text=name if name is not None else id, **kwargs)
        self.button.parent = self

        self.button.callbacks.click.register(self.open)

    # ------------------------------------------------------------------------------------------------------------------
    @abc.abstractmethod
    def onMessage(self, message, sender=None) -> None:
        if message['event'] == 'open':
            self.open(sender)

    # ------------------------------------------------------------------------------------------------------------------
    @abc.abstractmethod
    def getConfiguration(self):
        config = {
            'button': self.button.getPayload(),
            'popup': self.popup.getPayload(),
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> Application_Payload:
        """
        Returns the payload for the application.
        """
        return Application_Payload(id=self.uid,
                                   config=self.getConfiguration())

    # ------------------------------------------------------------------------------------------------------------------
    def getObjectByPath(self, path: str):
        """
        Returns the object at the given path.
        """
        # Check if it is the button
        if path == self.button.id:
            return self.button

        # Check if it is the popup
        id, remainder = split_path(path)
        if id == self.popup.id:
            return self.popup.getObjectByPath(remainder)
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def open(self, gui, sender=None, *args, **kwargs):
        """
        Opens the popup.
        """
        self.logger.debug(f"Opening popup {self.id} for client {sender}")
        if self.popup is None:
            self.logger.warning(f"Popup {self.id} not yet created")
            return

        self.gui = gui
        gui.openPopup(self.popup, sender)
        self.popup.callbacks.closed.register(self._onPopupClosed)

    # ------------------------------------------------------------------------------------------------------------------
    @abc.abstractmethod
    def _onPopupClosed(self, *args, **kwargs):
        ...
