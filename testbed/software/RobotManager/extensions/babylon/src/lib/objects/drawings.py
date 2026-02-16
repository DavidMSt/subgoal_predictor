"""Python-side wrappers for Babylon drawing objects (circle, line).

These correspond to BabylonCircleDrawing and BabylonLineDrawing in drawings.js,
registered in mapping.js as 'circle_drawing' and 'line_drawing'.
"""

from core.utils.dict import update_dict
from extensions.babylon.src.babylon import BabylonObject


class CircleDrawing(BabylonObject):
    """Floor-projected circle with translucent fill and opaque border.

    Matches the JS ``BabylonCircleDrawing`` (type = ``circle_drawing``).
    Position is ``[x, y]`` in z-up simulation coordinates.
    """
    type = 'circle_drawing'

    def __init__(self, object_id: str, x: float = 0, y: float = 0,
                 radius: float = 0.2,
                 fill_color: list | None = None,
                 border_color: list | None = None,
                 border_width: float = 0.02,
                 **kwargs):
        super().__init__(object_id, **kwargs)

        default_config = {
            'radius': radius,
            'circleFillColor': fill_color or [1, 1, 1, 0.15],
            'circleBorderColor': border_color or [1, 1, 1, 0.9],
            'circleBorderWidth': border_width,
        }
        self.config = update_dict(self.config, default_config, kwargs, allow_add=True)

        self._x = x
        self._y = y

    def setPosition(self, x: float, y: float):
        self._x = x
        self._y = y
        self.update()

    def setColor(self, fill_rgba: list | None = None, border_rgba: list | None = None):
        if fill_rgba is not None:
            self.config['circleFillColor'] = fill_rgba
        if border_rgba is not None:
            self.config['circleBorderColor'] = border_rgba
        self.updateConfig()

    def setRadius(self, radius: float):
        self.config['radius'] = radius
        self.updateConfig()

    def getConfig(self) -> dict:
        return {**self.config}

    def getData(self) -> dict:
        return {'position': [self._x, self._y, 0]}


class LineDrawing(BabylonObject):
    """Line segment drawn on the floor between two points.

    Matches the JS ``BabylonLineDrawing`` (type = ``line_drawing``).
    Start/end are ``[x, y]`` in z-up simulation coordinates.
    """
    type = 'line_drawing'

    def __init__(self, object_id: str,
                 start: list | None = None,
                 end: list | None = None,
                 color: list | None = None,
                 width: float = 0.02,
                 style: str = 'solid',
                 **kwargs):
        super().__init__(object_id, **kwargs)

        default_config = {
            'start': list(start) if start else [0, 0, 0],
            'end': list(end) if end else [1, 0, 0],
            'lineColor': color or [1, 1, 1, 0.95],
            'lineWidth': width,
            'lineStyle': style,
        }
        self.config = update_dict(self.config, default_config, kwargs, allow_add=True)

    def setEndpoints(self, start_xy: list, end_xy: list):
        s = list(start_xy) + [0] if len(start_xy) == 2 else list(start_xy)
        e = list(end_xy) + [0] if len(end_xy) == 2 else list(end_xy)
        self.config['start'] = s
        self.config['end'] = e
        self.updateConfig()

    def setColor(self, rgba: list):
        self.config['lineColor'] = rgba
        self.updateConfig()

    def getConfig(self) -> dict:
        return {**self.config}

    def getData(self) -> dict:
        return {
            'config': {
                'start': self.config['start'],
                'end': self.config['end'],
            }
        }
