from __future__ import annotations

import dataclasses
from typing import Any

from extensions.gui.src.lib.objects.objects import Widget


@dataclasses.dataclass
class LimboBilboConfig:
    wheel_radius: float = 0.06
    wheel_inner_ratio: float = 0.65
    body_height: float = 0.185
    body_width: float = 0.085
    body_corner_radius: float = 0.005
    tire_color: str | list = 'black'
    wheel_color: str | list = 'white'
    wheel_edge_color: str | list = dataclasses.field(default_factory=lambda: [0.3, 0.3, 0.3])
    body_color: str | list = dataclasses.field(default_factory=lambda: [0.3, 0.5, 0.9])
    body_edge_color: str | list = 'black'
    body_opacity: float = 0.9


class BilboLimboWidget(Widget):
    type = 'bilbo_limbo'

    def __init__(self, widget_id: str | None = None, **kwargs):
        super().__init__(widget_id, **kwargs)

        self._scene_config = {
            'x_range': kwargs.get('x_range', [-1.0, 1.0]),
            'floor_height': kwargs.get('floor_height', 0.04),
            'floor_color': kwargs.get('floor_color', [0.88, 0.88, 0.88]),
            'floor_edge_color': kwargs.get('floor_edge_color', [0.4, 0.4, 0.4]),
            'background_color': kwargs.get('background_color', [0.15, 0.15, 0.2]),
            'padding': kwargs.get('padding', 0.05),
            'show_grid': kwargs.get('show_grid', False),
            'grid_spacing': kwargs.get('grid_spacing', 0.1),
        }

        self._bilbos: dict[str, dict] = {}
        self._rectangles: dict[str, dict] = {}
        self._circles: dict[str, dict] = {}
        self._paths: dict[str, dict] = {}
        self._labels: dict[str, dict | None] = {'left': None, 'right': None}

    # === PUBLIC API ====================================================================================================

    def add_bilbo(self, bilbo_id: str, config: LimboBilboConfig | None = None, state: dict | None = None):
        if config is None:
            config = LimboBilboConfig()
        if state is None:
            state = {'x': 0.0, 'theta': 0.0}

        config_dict = dataclasses.asdict(config) if dataclasses.is_dataclass(config) else dict(config)
        self._bilbos[bilbo_id] = {'config': config_dict, 'state': state}
        self.function('add_bilbo', {'bilbo_id': bilbo_id, 'config': config_dict, 'state': state})

    def remove_bilbo(self, bilbo_id: str):
        self._bilbos.pop(bilbo_id, None)
        self.function('remove_bilbo', {'bilbo_id': bilbo_id})

    def update_bilbo(self, bilbo_id: str, x: float | None = None, theta: float | None = None):
        if bilbo_id in self._bilbos:
            if x is not None:
                self._bilbos[bilbo_id]['state']['x'] = x
            if theta is not None:
                self._bilbos[bilbo_id]['state']['theta'] = theta

        states = {}
        for bid, bdata in self._bilbos.items():
            states[bid] = bdata['state']

        self.sendUpdate({'bilbo_states': states})

    def add_rectangle(self, rect_id: str, x: float = 0.0, y: float = 0.0, width: float = 0.1, height: float = 0.1,
                      color: Any = None, edge_color: Any = None, edge_width: float = 1.0, opacity: float = 1.0):
        if color is None:
            color = [0.5, 0.5, 0.5]
        if edge_color is None:
            edge_color = [0.3, 0.3, 0.3]

        rect_data = {
            'x': x, 'y': y, 'width': width, 'height': height,
            'color': color, 'edge_color': edge_color, 'edge_width': edge_width, 'opacity': opacity,
        }
        self._rectangles[rect_id] = rect_data
        self.function('add_rectangle', {'rect_id': rect_id, **rect_data})

    def remove_rectangle(self, rect_id: str):
        self._rectangles.pop(rect_id, None)
        self.function('remove_rectangle', {'rect_id': rect_id})

    def update_rectangle(self, rect_id: str, **kwargs):
        if rect_id in self._rectangles:
            self._rectangles[rect_id].update(kwargs)
        self.function('update_rectangle', {'rect_id': rect_id, **kwargs})

    def add_circle(self, circle_id: str, x: float = 0.0, y: float = 0.0, radius: float = 0.05,
                   color: Any = None, edge_color: Any = None, edge_width: float = 1.0, opacity: float = 1.0):
        if color is None:
            color = [0.5, 0.5, 0.5]
        if edge_color is None:
            edge_color = [0.3, 0.3, 0.3]

        circle_data = {
            'x': x, 'y': y, 'radius': radius,
            'color': color, 'edge_color': edge_color, 'edge_width': edge_width, 'opacity': opacity,
        }
        self._circles[circle_id] = circle_data
        self.function('add_circle', {'circle_id': circle_id, **circle_data})

    def remove_circle(self, circle_id: str):
        self._circles.pop(circle_id, None)
        self.function('remove_circle', {'circle_id': circle_id})

    def update_circle(self, circle_id: str, **kwargs):
        if circle_id in self._circles:
            self._circles[circle_id].update(kwargs)
        self.function('update_circle', {'circle_id': circle_id, **kwargs})

    def add_path(self, path_id: str, x: list | Any = None, y: list | Any = None,
                 color: Any = None, width: float = 2.0, opacity: float = 1.0,
                 dash: list | None = None,
                 gradient: bool = False, gradient_start_color: Any = None, gradient_end_color: Any = None):
        if x is None:
            x = []
        if y is None:
            y = []
        if color is None:
            color = [0.2, 0.5, 1.0]
        # Convert numpy arrays to lists for JSON serialization
        x_list = list(x) if not isinstance(x, list) else x
        y_list = list(y) if not isinstance(y, list) else y

        path_data = {
            'x': x_list, 'y': y_list, 'color': color, 'width': width,
            'opacity': opacity, 'dash': dash, 'gradient': gradient,
            'gradient_start_color': gradient_start_color, 'gradient_end_color': gradient_end_color,
        }
        self._paths[path_id] = path_data
        self.function('add_path', {'path_id': path_id, **path_data})

    def remove_path(self, path_id: str):
        self._paths.pop(path_id, None)
        self.function('remove_path', {'path_id': path_id})

    def update_path(self, path_id: str, x: list | Any = None, y: list | Any = None, **kwargs):
        if path_id in self._paths:
            if x is not None:
                kwargs['x'] = list(x) if not isinstance(x, list) else x
            if y is not None:
                kwargs['y'] = list(y) if not isinstance(y, list) else y
            self._paths[path_id].update(kwargs)
        self.function('update_path', {'path_id': path_id, **kwargs})

    def set_label(self, side: str, text: str, color: Any = None, font_size: float = 14,
                  font_weight: str = 'normal', font_family: str = 'sans-serif', opacity: float = 1.0):
        if color is None:
            color = [1.0, 1.0, 1.0]
        label_data = {
            'text': text, 'color': color, 'font_size': font_size,
            'font_weight': font_weight, 'font_family': font_family, 'opacity': opacity,
        }
        self._labels[side] = label_data
        self.function('set_label', {'side': side, **label_data})

    def clear_label(self, side: str):
        self._labels[side] = None
        self.function('clear_label', {'side': side})

    def set_x_range(self, x_min: float, x_max: float):
        self._scene_config['x_range'] = [x_min, x_max]
        self.function('set_x_range', {'x_range': [x_min, x_max]})

    def set_grid(self, show: bool | None = None, spacing: float | None = None):
        if show is not None:
            self._scene_config['show_grid'] = show
        if spacing is not None:
            self._scene_config['grid_spacing'] = spacing
        self.function('set_grid', {
            'show_grid': self._scene_config['show_grid'],
            'grid_spacing': self._scene_config['grid_spacing'],
        })

    # === WIDGET INTERFACE =============================================================================================

    def getConfiguration(self) -> dict:
        config = {
            **self._scene_config,
            'bilbos': {bid: bdata for bid, bdata in self._bilbos.items()},
            'rectangles': {rid: rdata for rid, rdata in self._rectangles.items()},
            'circles': {cid: cdata for cid, cdata in self._circles.items()},
            'paths': {pid: pdata for pid, pdata in self._paths.items()},
            'labels': {side: ldata for side, ldata in self._labels.items() if ldata is not None},
        }
        return config

    def handleEvent(self, message, sender=None) -> None:
        self.logger.debug(f"BilboLimboWidget received event: {message}")
