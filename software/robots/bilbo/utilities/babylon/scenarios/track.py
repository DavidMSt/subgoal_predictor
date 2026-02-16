from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

from extensions.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.babylon.src.scenarios.scenario import BabylonScenario

if TYPE_CHECKING:
    from extensions.babylon.src.babylon import BabylonVisualization


class TrackScenario(BabylonScenario):
    """Straight track scenario — floor only, no walls.

    A long narrow track (default x=[-0.25, 2.75], y=[-0.25, 0.25]) with tiled
    floor. Objects stored in self.objects with key: floor.
    """

    def __init__(self,
                 x_range: list | None = None,
                 y_range: list | None = None,
                 floor_texture: str = 'floor_bright.png',
                 background_color: list | None = None,
                 camera_radius: float | None = None,
                 camera_alpha: float | None = None,
                 camera_beta: float | None = None,
                 camera_target: list | None = None,
                 show_coordinate_system: bool = False,
                 fog: bool = True,
                 lights: dict | None = None):
        super().__init__()

        if camera_alpha is None:
            camera_alpha = 1.7743
        if camera_beta is None:
            camera_beta = 1.0168
        if camera_radius is None:
            camera_radius = 1.51
        if camera_target is None:
            camera_target = [0.95, 0.07, 0.02]

        self.x_range = x_range if x_range is not None else [-0.25, 2.75]
        self.y_range = y_range if y_range is not None else [-0.25, 0.25]
        self.floor_texture = floor_texture
        self.background_color = background_color
        self.camera_radius = camera_radius
        self.camera_alpha = camera_alpha
        self.camera_beta = camera_beta
        self.camera_target = camera_target
        self.show_coordinate_system = show_coordinate_system
        self.fog = fog
        self.lights = lights

        # Derived dimensions
        self.length_x = self.x_range[1] - self.x_range[0]
        self.length_y = self.y_range[1] - self.y_range[0]
        self.center_x = (self.x_range[0] + self.x_range[1]) / 2
        self.center_y = (self.y_range[0] + self.y_range[1]) / 2

    def get_config(self) -> dict:
        config = {}

        config['show_coordinate_system'] = self.show_coordinate_system

        if self.background_color is not None:
            config['background_color'] = self.background_color

        # Camera defaults: look at track center, pull back enough to see the whole track
        camera = {
            'target': [self.center_x, self.center_y, 0],
            'radius': max(self.length_x, self.length_y) * 1.0,
        }
        if self.camera_radius is not None:
            camera['radius'] = self.camera_radius
        if self.camera_alpha is not None:
            camera['alpha'] = self.camera_alpha
        if self.camera_beta is not None:
            camera['beta'] = self.camera_beta
        if self.camera_target is not None:
            camera['target'] = self.camera_target
        config['camera'] = camera

        if not self.fog:
            config['scene'] = {'add_fog': False}

        # Default lights: main directional shines from behind the camera so the
        # visible side of objects on the track is lit, not shadowed.
        lights = {'directional_direction': [1, 1, -1]}
        if self.lights is not None:
            lights.update(self.lights)
        config['lights'] = lights

        return config

    def setup(self, babylon: BabylonVisualization):
        super().setup(babylon)

        # Floor — use [min, max] range format, tile_size derived from y extent (1 tile in y)
        tile_size = self.length_y
        floor = SimpleFloor('floor',
                            size_x=self.x_range,
                            size_y=self.y_range,
                            tile_size=tile_size,
                            texture=self.floor_texture)
        babylon.addObject(floor)
        self.objects['floor'] = floor


if __name__ == '__main__':
    from extensions.babylon.src.standalone import StandaloneBabylon
    from extensions.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo

    scenario = TrackScenario(background_color=[1, 1, 1])
    babylon = StandaloneBabylon(title="Track Scenario", ws_port=9000, http_port=9200,
                                scenario=scenario)
    babylon.start()

    robot = BabylonBilbo('bilbo1', color=[0.7, 0.1, 0.1], text='1')
    babylon.addObject(robot)

    t0 = time.time()
    try:
        while True:
            t = time.time() - t0
            # Drive back and forth along the track
            x = 1.25 + 1.0 * math.sin(0.4 * t)
            robot.set_state(
                x=x,
                y=0,
                theta=0 if math.cos(0.4 * t) > 0 else math.pi,
                psi=0.03 * math.sin(3 * t),
            )
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        babylon.close()
