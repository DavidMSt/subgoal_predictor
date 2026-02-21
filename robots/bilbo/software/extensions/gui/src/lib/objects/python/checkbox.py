from core.utils.callbacks import CallbackContainer, callback_definition
from core.utils.events import Event, event_definition
from extensions.gui.src.lib.objects.objects import Widget


@callback_definition
class CheckboxWidgetCallbacks:
    changed: CallbackContainer


@event_definition
class CheckboxWidgetEvents:
    changed: Event


class CheckboxWidget(Widget):
    type = 'checkbox'
    callbacks: CheckboxWidgetCallbacks
    value: bool

    config: dict

    # === INIT =========================================================================================================
    def __init__(self, widget_id: str, value: bool, config: dict = None, **kwargs):
        super().__init__(widget_id, **kwargs)

        default_config = {
            'color': [0, 0, 0, 0],
            'text_color': [0.8, 0.8, 0.8, 1],
            'title': 'Checkbox:',
            'title_position': 'left',  # 'top' or 'left'
            'tooltip': None,

            'checkbox_border_color': '#999',
            'checkbox_background_color': [1, 1, 1, 0.1],
            'checkbox_check_color': [0, 1, 0, 1],
            'checkbox_size': '16pt',
            'margin_right': '10px',
        }

        self.config = {**default_config, **self.config, **(config or {}), **kwargs}
        self.callbacks = CheckboxWidgetCallbacks()
        self.events = CheckboxWidgetEvents()

        self.value = value

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def value(self) -> bool:
        return self._value

    @value.setter
    def value(self, new_value: bool):
        self._value = new_value
        self._sendValueToFrontend(new_value)
        self.callbacks.changed.call(new_value)

    # ------------------------------------------------------------------------------------------------------------------
    def _sendValueToFrontend(self, value):
        self.function(
            function_name='setValue',
            args=value
        )

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        """
        Returns a dictionary describing this widget’s state for front-end rendering.
        """
        config = {
            'type': 'checkbox',
            'id': self.id,
            'value': self.value,
            **self.config,
        }

        return config

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message: dict, sender=None) -> None:
        self.logger.debug(f"Received message: {message}")

        if 'event' not in message:
            self.logger.warning(f"Unknown message received: {message}")
            return
        event = message['event']

        match event:
            case 'checkbox_change':
                self.value = message['data']['value']
                self.accept(True, sender)
            case _:
                self.logger.warning(f"Unknown event message received: {message}")
                return

    # ------------------------------------------------------------------------------------------------------------------
    def init(self, *args, **kwargs):
        pass
