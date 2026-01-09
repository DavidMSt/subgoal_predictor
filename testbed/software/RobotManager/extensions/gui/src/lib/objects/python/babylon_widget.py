from core.utils.dict import update_dict
from extensions.babylon.src.babylon import BabylonVisualization
from extensions.gui.src.lib.objects.objects import Widget


class BabylonWidget(Widget):
    type = 'babylon_widget'

    babylon: BabylonVisualization | None = None

    # === INIT =========================================================================================================
    def __init__(self, widget_id: str, **kwargs):
        super().__init__(widget_id, **kwargs)

        default_config = {
            'babylon_id': 'babylon'
        }

        self.config = update_dict(default_config, kwargs)

    # === METHODS ======================================================================================================
    def getConfiguration(self) -> dict:
        config = {
            **self.config
        }
        return config

    def getPayload(self):
        payload = super().getPayload()
        payload['babylon'] = self.babylon.getPayload() if self.babylon else None
        return payload

    def handleEvent(self, message, sender=None) -> None:
        pass

    def set_babylon(self, babylon: BabylonVisualization) -> None:
        self.babylon = babylon
    # === PRIVATE METHODS ==============================================================================================
