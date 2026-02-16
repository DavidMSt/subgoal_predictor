from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

import numpy as np
import qmt

from extensions.babylon.src.lib.objects.box.box import Box
from extensions.babylon.src.lib.objects.cylinder.cylinder import Cylinder
from extensions.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.babylon.src.scenarios.scenario import BabylonScenario

if TYPE_CHECKING:
    from extensions.babylon.src.babylon import BabylonVisualization


class TrackLimboScenario(BabylonScenario):
    """Track with a limbo bar — two posts and a glowing cylinder across the track.

    The limbo gate is placed at the x-midpoint of the track. Two translucent
    posts sit at the track edges, connected by a red glowing cylinder bar at
    the configured limbo height.

    Objects stored in self.objects with keys: floor, post_left, post_right, bar.
    """

    def __init__(self,
                 limbo_height: float = 0.15,
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

        self.limbo_height = limbo_height
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

        lights = {'directional_direction': [1, 1, -1]}
        if self.lights is not None:
            lights.update(self.lights)
        config['lights'] = lights

        return config

    def setup(self, babylon: BabylonVisualization):
        super().setup(babylon)

        # Floor
        tile_size = self.length_y
        floor = SimpleFloor('floor',
                            size_x=self.x_range,
                            size_y=self.y_range,
                            tile_size=tile_size,
                            texture=self.floor_texture)
        babylon.addObject(floor)
        self.objects['floor'] = floor

        # Limbo gate at the x-midpoint
        gate_x = self.center_x
        post_thickness = 0.02
        post_height = self.limbo_height + 0.02  # slightly taller than the bar

        # Posts at the y-edges, offset inward by half their width so they don't protrude
        half_t = post_thickness / 2
        for post_id, y in [('post_left', self.y_range[0] + half_t),
                           ('post_right', self.y_range[1] - half_t)]:
            post = Box(post_id,
                       size={'x': post_thickness, 'y': post_thickness, 'z': post_height},
                       color=[0.6, 0.6, 0.6],
                       alpha=0.9)
            post.setPosition(x=gate_x, y=y, z=post_height / 2)
            babylon.addObject(post)
            self.objects[post_id] = post

        # Glowing cylinder bar between the posts at limbo height
        bar_length = self.length_y - post_thickness
        bar = Cylinder('bar',
                       color=[1, 0, 0],
                       diameter=0.0125,
                       height=bar_length,
                       alpha=0.9)
        bar.setOrientation(qmt.quatFromAngleAxis(np.pi / 2, [1, 0, 0]))
        bar.setPosition(x=gate_x, y=self.center_y, z=self.limbo_height)
        babylon.addObject(bar)
        self.objects['bar'] = bar


if __name__ == '__main__':
    from extensions.babylon.src.standalone import StandaloneBabylon
    from extensions.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo

    scenario = TrackLimboScenario(limbo_height=0.15, background_color=[1, 1, 1])
    babylon = StandaloneBabylon(title="Track Limbo Scenario", ws_port=9000, http_port=9200,
                                scenario=scenario)
    babylon.start()

    robot = BabylonBilbo('bilbo1', color=[0.7, 0.1, 0.1], text='1')
    babylon.addObject(robot)

    t0 = time.time()
    try:
        while True:
            t = time.time() - t0
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
