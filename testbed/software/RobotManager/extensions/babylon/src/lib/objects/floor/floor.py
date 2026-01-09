from core.utils.dict import update_dict
from extensions.babylon.src.babylon import BabylonObject


class SimpleFloor(BabylonObject):
    type = 'floor_simple'
    pollable = False

    def __init__(self, object_id: str, **kwargs):
        super().__init__(object_id, **kwargs)

        default_config = {
            'size_x': 5,
            'size_y': 5,
            'tile_size': 0.5,
            'texture': 'floor_bright.png',
            'offset_x': 0,
            'offset_y': 0,
            'origin': 'center'  # 'center' or 'corner'
        }

        self.config = update_dict(default_config, kwargs)

    # ------------------------------------------------------------------------------------------------------------------
    def getConfig(self) -> dict:
        config = {
            **self.config,
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getData(self) -> dict:
        return {}
