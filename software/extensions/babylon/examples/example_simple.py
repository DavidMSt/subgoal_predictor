import time

import numpy as np

from extensions.babylon.src.babylon import BabylonVisualization
from extensions.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo
from extensions.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.babylon.src.lib.objects.box.box import Box, Wall, WallFancy


def example_simple_1():
    babylon = BabylonVisualization(id='babylon', host='localhost', port=9000)
    babylon.init()
    babylon.start()

    floor = SimpleFloor('floor', size_y=50, size_x=50, texture='floor_bright.png')
    babylon.addObject(floor)

    box1 = Box('box1', size={'x': 0.1, 'y': 0.1, 'z': 0.1}, alpha=0.6)
    babylon.addObject(box1)

    wall1 = WallFancy('wall1', length=3, texture='wood4.png', include_end_caps=True)
    wall1.setPosition(y=1.5)
    babylon.addObject(wall1)

    wall2 = WallFancy('wall2', length=3, texture='wood4.png', include_end_caps=True)
    babylon.addObject(wall2)
    wall2.setPosition(y=-1.5)

    wall3 = WallFancy('wall3', length=3, texture='wood4.png')
    wall3.setPosition(x=1.5)
    wall3.setAngle(np.pi / 2)
    babylon.addObject(wall3)

    wall4 = WallFancy('wall4', length=3, texture='wood4.png')
    wall4.setPosition(x=-1.5)
    wall4.setAngle(np.pi / 2)
    babylon.addObject(wall4)

    bilbo1 = BabylonBilbo('bilbo1', color=[156 / 255, 98 / 255, 98 / 255], )
    babylon.addObject(bilbo1)

    bilbo1.setPosition(y=1)
    bilbo1.set_state(theta=np.pi / 4, psi=np.pi / 4)

    bilbo2 = BabylonBilbo('bilbo2', color=[100 / 255, 125 / 255, 156 / 255], text='2', y=-0.5)
    babylon.addObject(bilbo2)

    bilbo3 = BabylonBilbo('bilbo3', color=[78 / 255, 115 / 255, 78 / 255], text='3', x=-0.5)
    babylon.addObject(bilbo3)

    box1.setPosition(z=0.2)

    while True:
        # box1.setPosition(x=box1.data.x + 0.01)
        # box1.setPosition(y=box1.data.y + 0.01)
        # if box1.data.x > 1:
        #     box1.setPosition(x=0, y=0)
        time.sleep(0.01)


if __name__ == '__main__':
    example_simple_1()
