from typing import Any, Callable, Optional

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.logging_utils import Logger
from extensions.gui.src.lib.objects.objects import Widget
from extensions.gui.src.lib.utilities import warn_on_unknown_kwargs


@callback_definition
class InputWidgetCallbacks:
    """
    Defines callbacks for TextInputWidget:
      - text_changed: fired when the user commits a new valid text (e.g. on Enter)
      - invalid_input: fired when the user’s input fails validation
    """
    value_changed: CallbackContainer


class InputWidget(Widget):
    """
    A single-line text‐input widget. Supports optional datatype enforcement ('int' or 'float')
    and/or a custom validator function. Fires `text_changed` when a new valid value is committed,
    or `invalid_input` if the entered text does not pass validation. Replies to the front-end
    with either an 'accept_value' or 'reject_value' message. Also supports a custom tooltip.
    """

    # def getConfiguration(self) -> dict:
    #     pass
    #
    # def init(self, *args, **kwargs):
    #     pass

    type = "input"
    callbacks: InputWidgetCallbacks

    def __init__(
            self,
            widget_id: str,
            *,
            value: Any = None,
            datatype: Any = None,  # 'int' | 'float' | None
            validator: Optional[Callable[[Any], bool]] = None,
            config: Optional[dict] = None,
            **kwargs
    ):
        super().__init__(widget_id)

        self.logger = Logger(f"TextInputWidget {self.id}", "DEBUG")
        self.callbacks = InputWidgetCallbacks()

        # Merge default_config, passed‐in config, and any extra kwargs
        if config is None:
            config = {}

        default_config = {
            "title": None,  # defaults to widget_id if None
            "title_position": "top",  # 'top' or 'left'
            "visible": True,
            "color": "transparent",
            "text_color": [1, 1, 1],
            "inputFieldColor": [1, 1, 1, 0.8],
            "inputFieldTextColor": [0, 0, 0],
            "inputFieldFontSize": 11,
            "inputFieldAlign": "center",
            "inputFieldWidth": "100%",
            "inputFieldPosition": "center",
            "tooltip": None,  # custom tooltip text
        }

        self.config = {**default_config, **config, **kwargs}

        warn_on_unknown_kwargs(kwargs, default_config, self.logger)

        if self.config["title"] is None:
            self.config["title"] = self.id

        # Core properties managed separately
        self._value = value
        self.datatype = datatype
        self.validator = validator

        if self.config['tooltip'] is None:
            self.config['tooltip'] = f"Datatype: {self.datatype}"

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def value(self) -> Any:
        return self._value

    @value.setter
    def value(self, value: Any):
        self.setValue(value)

    # ------------------------------------------------------------------------------------------------------------------
    def setValue(self, value: Any, send_update: bool = True):

        # 1. Check if the value would be valid
        value, valid, message = self._checkValue(value)

        # 2. If the value is valid, set it
        if valid:
            self._value = value
        else:
            return False, message

        # Send an update
        if send_update:
            self.updateConfig()

        self.callbacks.value_changed.call(self._value)

        return True, None

    # ------------------------------------------------------------------------------------------------------------------
    def _checkValue(self, value):
        if isinstance(value, str):
            value = value.strip()

        normalized_value = None

        if self.datatype == 'int':

            if isinstance(value, int):
                return value, True, None

            # Quick check: a valid integer literal
            if not value or not value.lstrip("+-").isdigit():
                self.logger.debug(f"Invalid int input: {value!r}")
                return None, False, f"Could not parse int: {value!r}"

            try:
                normalized_int = int(value)
            except Exception:
                self.logger.debug(f"Could not parse int: {value!r}")
                return None, False, f"Could not parse int: {value!r}"

            normalized_value = normalized_int

        elif self.datatype == "float":
            try:
                normalized_float = float(value)
            except ValueError:
                self.logger.debug(f"Invalid float input: {value!r}")
                return None, False, f"Could not parse float: {value!r}"

            normalized_value = normalized_float

        else:
            # No datatype enforcement: keep as raw string
            normalized_value = value

        # Custom validator (accepts the typed value)
        if self.validator is not None:
            try:
                valid = self.validator(normalized_value)
            except Exception as e:
                self.logger.debug(f"Validator exception on {normalized_value!r}: {e}")
                valid = False

            if not valid:
                self.logger.debug(f"Validator rejected input: {normalized_value!r}")
                return None, False, f"Validator rejected input: {normalized_value!r}"

        return normalized_value, True, None

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message: dict, sender=None) -> Any:
        """
        Handle incoming messages from the front‐end. Expected message shape:
          { "event": "text_input_commit", "data": { "value": entered_string } }
        Attempts to cast the entered string into the specified datatype (int/float) or leaves as string.
        Fires callbacks with the typed value on success, or invalid_input on failure.
        """
        self.logger.debug(f"Received message: {message}")

        event = message.get("event")
        data = message.get("data", {})

        if event == "text_input_commit":
            valid, message = self.setValue(data['value'], send_update=False)

            self.function(function_name='validateInput',
                          args={'valid': valid, 'value': self._value, 'message': message})

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        """
        Return a dict of all parameters that the front‐end needs to render/update this widget.
        We include 'value' here so that the JS side can initialize the input field correctly,
        as well as 'datatype' and 'tooltip' for client-side behavior.
        """
        config = {
            'type': self.type,
            'id': self.id,
            'value': self._value,
            'datatype': self.datatype,
            **self.config,
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def init(self, *args, **kwargs):
        """
        Called once when the GUI is first constructed. Optionally, push initial configuration here.
        If your framework requires an explicit push, uncomment the sendUpdate line below.
        """
        # self.sendUpdate(self.getConfiguration())
        pass
