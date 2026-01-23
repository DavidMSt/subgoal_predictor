from typing import Any, Optional, List

from core.utils.callbacks import callback_definition, CallbackContainer
from extensions.gui.src.lib.objects.objects import Widget


@callback_definition
class RotaryDialWidgetCallbacks:
    value_changed: CallbackContainer


class RotaryDialWidget(Widget):
    type = 'rotary_dial'

    # === INIT =========================================================================================================
    def __init__(
            self,
            widget_id: str,
            min_value: float = 0,
            max_value: float = 100,
            increment: float = 1,
            value: float = 0,
            config: Optional[dict] = None,
            **kwargs
    ):
        super().__init__(widget_id)

        if config is None:
            config = {}

        # Default configuration parameters
        default_config = {
            'title': None,
            'titlePosition': 'top',  # 'top' or 'left'
            'visible': True,
            'color': '#333',
            'dialColor': '#3399FF',
            'text_color': '#fff',
            'ticks': [],  # List[float]
            'continuousUpdates': False,
            'limitToTicks': False,
            'dialWidth': 5,  # thickness of the dial arc
        }

        # Merge defaults, provided config, and any extra kwargs
        self.config = {**default_config, **config, **kwargs}

        self.callbacks = RotaryDialWidgetCallbacks()

        # If no title given, default to widget_id
        if self.config.get('title') is None:
            self.config['title'] = self.id

        # Enforce a valid titlePosition
        tp = self.config.get('titlePosition', 'top')
        self.config['titlePosition'] = 'left' if tp == 'left' else 'top'

        # Numeric metadata
        self.increment = increment
        self.min_value = self._parseValue(min_value, increment=self.increment)
        self.max_value = self._parseValue(max_value, increment=self.increment)

        # Initialize the current value (clamped/rounded by setter)
        self._value: float = 0.0
        self.value = value  # invokes setter

        # Validate and normalize ticks
        ticks = self.config.get('ticks', [])
        if not isinstance(ticks, list):
            raise ValueError("`ticks` must be a list of numbers.")
        normalized_ticks: List[float] = []
        for t in ticks:
            normalized_ticks.append(
                self._parseValue(t, self.min_value, self.max_value, self.increment)
            )
        self.config['ticks'] = normalized_ticks

        self.callbacks = RotaryDialWidgetCallbacks()

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, new_value: float):
        """
        Round and clamp new_value to [min_value, max_value] in steps of increment.
        """
        self._value = self._parseValue(
            new_value,
            self.min_value,
            self.max_value,
            self.increment
        )

        self._sendValueToFrontend(self.value)
        self.callbacks.value_changed.call(self.value)

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        """
        Return a dictionary of parameters needed by the front-end to render/update the rotary dial.
        """
        return {
            'min': self.min_value,
            'max': self.max_value,
            'value': self.value,
            'increment': self.increment,
            **self.config
        }

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message: Any, sender=None) -> Any:
        """
        Handle incoming messages from the front-end. For example, when the user drags or clicks
        the rotary dial, the message might be {'event': 'rotary_dial_change', 'value': new_value}.
        """
        self.logger.debug(f"Received message: {message}")

        if 'event' not in message:
            self.logger.warning(f"Unknown message received: {message}")
            return

        match message['event']:
            case 'rotary_dial_change':
                self.value = float(message['data']['value'])

    # ------------------------------------------------------------------------------------------------------------------
    def init(self, *args, **kwargs):
        """
        Called once when the GUI is first constructed. You could push the initial configuration
        to the front-end here if needed.
        """
        pass

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _parseValue(
            value: float,
            min_value: Optional[float] = None,
            max_value: Optional[float] = None,
            increment: float = 1
    ) -> float:
        """
        Round `value` to the nearest multiple of `increment`, then clamp it into [min_value, max_value].
        """
        if increment <= 0:
            raise ValueError("Increment must be greater than 0.")

        # Round to nearest increment
        rounded = round(value / increment) * increment

        # Clamp to [min_value, max_value] if provided
        if min_value is not None:
            rounded = max(rounded, min_value)
        if max_value is not None:
            rounded = min(rounded, max_value)

        return rounded

    # ------------------------------------------------------------------------------------------------------------------
    def _sendValueToFrontend(self, value):
        self.function(
            function_name='setValue',
            args=value
        )
