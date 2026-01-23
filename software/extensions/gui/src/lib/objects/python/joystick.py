from typing import Any, Optional, Literal

from core.utils.callbacks import callback_definition, CallbackContainer
from extensions.gui.src.lib.objects.objects import Widget


# ======================================================================================================================
@callback_definition
class JoystickWidgetCallbacks:
    position_changed: CallbackContainer
    long_click: CallbackContainer


class JoystickWidget(Widget):
    """
    A touch joystick widget that sends (x, y) position when changed.

    Features:
    - Continuous position updates while dragging
    - Configurable axis constraints (horizontal, vertical, or both)
    - Return-to-center on release (configurable)
    - Deadzone support
    - Throttled update rate
    """

    type = 'joystick'
    callbacks: JoystickWidgetCallbacks

    def __init__(
            self,
            widget_id: str,
            fixed_axis: Optional[Literal['horizontal', 'vertical']] = None,
            return_to_center: bool = True,
            config: Optional[dict] = None,
            **kwargs
    ):
        super().__init__(widget_id)

        if config is None:
            config = {}

        default_config = {
            'title': None,
            'color': [0.2, 0.2, 0.2],
            'knob_color': [0.6, 0.6, 0.6],
            'base_color': [0.35, 0.35, 0.35],
            'text_color': [1, 1, 1],
            'continuous_updates': True,
            'max_updates_per_second': 20,
            'show_values': False,
            'deadzone': 0,
        }

        self.config = {**default_config, **config, **kwargs}
        self.callbacks = JoystickWidgetCallbacks()

        if self.config['title'] is None:
            self.config['title'] = self.id

        self.fixed_axis = fixed_axis
        self.return_to_center = return_to_center

        # Current position (-1 to 1 range)
        self._x = 0.0
        self._y = 0.0

    # ==================================================================================================================
    @property
    def x(self) -> float:
        return self._x

    @property
    def y(self) -> float:
        return self._y

    @property
    def position(self) -> tuple[float, float]:
        return (self._x, self._y)

    # ==================================================================================================================
    def getConfiguration(self) -> dict:
        config = {
            'x': self._x,
            'y': self._y,
            'fixed_axis': self.fixed_axis,
            'return_to_center': self.return_to_center,
            **self.config
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def set_position(self, x: float, y: float):
        """
        Set the joystick position programmatically.

        Args:
            x: X position (-1 to 1)
            y: Y position (-1 to 1)
        """
        # Clamp values
        x = max(-1.0, min(1.0, x))
        y = max(-1.0, min(1.0, y))

        # Apply axis constraint
        if self.fixed_axis == 'horizontal':
            y = 0.0
        elif self.fixed_axis == 'vertical':
            x = 0.0

        self._x = x
        self._y = y

        # Send to frontend
        self._sendPositionToFrontend(x, y)

    # ------------------------------------------------------------------------------------------------------------------
    def _sendPositionToFrontend(self, x: float, y: float):
        self.sendUpdate({'x': x, 'y': y})

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> Any:
        if 'event' not in message:
            self.logger.warning(f"Got unknown message: {message}")
            return

        match message['event']:
            case 'joystick_change':
                try:
                    x = float(message['data']['x'])
                    y = float(message['data']['y'])

                    # Update internal state
                    self._x = x
                    self._y = y

                    # Call the callback
                    self.callbacks.position_changed.call(x, y)
                except (TypeError, KeyError) as e:
                    self.logger.warning(f"Got invalid joystick data: {message['data']}, error: {e}")

            case 'joystick_long_click':
                self.callbacks.long_click.call()

            case _:
                self.logger.warning(f"Got unknown event: {message['event']}")

    # ------------------------------------------------------------------------------------------------------------------
    def init(self, *args, **kwargs):
        pass
