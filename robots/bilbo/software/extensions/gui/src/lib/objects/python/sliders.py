from typing import Any, Optional

from core.utils.callbacks import callback_definition, CallbackContainer
from extensions.gui.src.lib.objects.objects import Widget


# ======================================================================================================================
@callback_definition
class SliderWidgetCallbacks:
    value_changed: CallbackContainer
    click: CallbackContainer


class SliderWidget(Widget):
    type = 'slider'
    callbacks: SliderWidgetCallbacks

    def __init__(self, widget_id, min_value=0, max_value=10, increment=1, value=0, config=None, **kwargs):
        super().__init__(widget_id)

        if config is None:
            config = {}

        default_config = {
            'title': None,
            'color': [0.7, 0.7, 0.7],
            'text_color': [1, 1, 1],
            'fontSize': 12,
            'direction': 'horizontal',
            'continuousUpdates': False,
            'ticks': None,
            'snapToTicks': False,
            'automaticResetValue': None,
        }

        self.config = {**default_config, **config, **kwargs}

        self.callbacks = SliderWidgetCallbacks()

        if self.config['title'] is None:
            self.config['title'] = self.id

        self.increment = increment
        self.min_value = self._parseValue(min_value, increment=self.increment)
        self.max_value = self._parseValue(max_value, increment=self.increment)
        self.value = value
        if self.config['ticks'] is not None:
            if not isinstance(self.config['ticks'], list):
                raise ValueError('ticks must be a list')

            for i, tick in enumerate(self.config['ticks']):
                self.config['ticks'][i] = self._parseValue(tick, increment=self.increment)

    # ==================================================================================================================
    def getConfiguration(self) -> dict:
        config = {
            'value': self.value,
            'min_value': self.min_value,
            'max_value': self.max_value,
            'increment': self.increment,
            **self.config
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = self._parseValue(value, self.min_value, self.max_value, self.increment)
        self._sendValueToFrontend(self.value)
        self.callbacks.value_changed.call(self.value)

    # ------------------------------------------------------------------------------------------------------------------
    def _sendValueToFrontend(self, value):
        self.sendUpdate(value)

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> Any:
        if 'event' not in message:
            self.logger.warning(f"Got unknown message: {message}")

        match message['event']:
            case 'slider_change':
                try:
                    self.value = float(message['data']['value'])
                except TypeError:
                    self.logger.warning(f"Got invalid value: {message['data']['value']}")
                    print(message)
            case _:
                self.logger.warning(f"Got unknown message: {message}")

    # ------------------------------------------------------------------------------------------------------------------
    def init(self, *args, **kwargs):
        pass

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _parseValue(value, min_value=None, max_value=None, increment=1):
        if increment <= 0:
            raise ValueError("Increment must be greater than 0")

        # Round to the nearest increment
        rounded = round(value / increment) * increment

        # Clamp to min and max if they are not None
        if min_value is not None:
            rounded = max(rounded, min_value)
        if max_value is not None:
            rounded = min(rounded, max_value)
        return rounded


# ======================================================================================================================
@callback_definition
class ClassicSliderWidgetCallbacks:
    value_changed: CallbackContainer
    click: CallbackContainer


class ClassicSliderWidget(Widget):
    """
    A “classic” slider widget with configurable title, colors, tick marks, snapping, and automatic reset.
    """

    type = 'classic_slider'

    callbacks: ClassicSliderWidgetCallbacks

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
            'titlePosition': 'top',  # 'top' | 'bottom' | 'left' | 'right'
            'valuePosition': 'center',  # 'top' | 'bottom' | 'left' | 'right' | 'center'
            'visible': True,
            'backgroundColor': '#444',
            'stemColor': '#888',
            'handleColor': '#ccc',
            'text_color': '#fff',
            'direction': 'horizontal',  # 'horizontal' | 'vertical'
            'continuousUpdates': False,
            'snapToTicks': False,
            'ticks': [],  # List[float]
            'automaticResetValue': None  # float or None
        }

        # Merge defaults, config dict, and any extra kwargs
        self.config = {**default_config, **(config or {}), **kwargs}

        self.callbacks = ClassicSliderWidgetCallbacks()

        # If title was not provided, default to the widget ID
        if self.config.get('title') is None:
            self.config['title'] = self.id

        # Store numeric slider metadata
        self.increment = increment
        self.min_value = self._parseValue(min_value, increment=self.increment)
        self.max_value = self._parseValue(max_value, increment=self.increment)

        # Initialize current value (will be clamped and rounded by setter)
        self._value = 0.0
        self.value = value  # invokes the setter

        # Validate and normalize tick marks, if any
        if self.config.get('ticks') is not None:
            if not isinstance(self.config['ticks'], list):
                raise ValueError('`ticks` must be a list of numbers.')
            normalized_ticks: list[float] = []
            for tick in self.config['ticks']:
                # Round each tick to the nearest increment and clamp
                normalized_ticks.append(self._parseValue(tick, self.min_value, self.max_value, self.increment))
            self.config['ticks'] = normalized_ticks

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, new_value: float):
        """
        Parse, round, and clamp the new_value to [min_value, max_value] in steps of increment.
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
        Return a dictionary of all parameters that the front-end needs to render/update this classic slider.
        """
        return {
            'min_value': self.min_value,
            'max_value': self.max_value,
            'value': self.value,
            'increment': self.increment,
            **self.config,
        }

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> Any:
        if 'event' not in message:
            self.logger.warning(f"Got unknown message: {message}")

        match message['event']:
            case 'slider_change':
                self.value = float(message['data']['value'])

    # ------------------------------------------------------------------------------------------------------------------
    def init(self, *args, **kwargs):
        """
        Called once when the GUI is first being constructed. You could push the initial configuration
        to the front-end here if that’s how your framework works.
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

        # Round to the nearest increment
        rounded = round(value / increment) * increment

        # Clamp to [min_value, max_value] if provided
        if min_value is not None:
            rounded = max(rounded, min_value)
        if max_value is not None:
            rounded = min(rounded, max_value)

        return rounded

    # ------------------------------------------------------------------------------------------------------------------
    def _sendValueToFrontend(self, value):
        self.sendUpdate(value)

