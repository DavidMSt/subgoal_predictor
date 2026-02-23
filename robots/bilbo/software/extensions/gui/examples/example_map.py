import math
import time

from core.utils.network.network import getHostIP
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.map.map import MapWidget
from extensions.gui.src.lib.map.map_objects import Point, Circle, Agent, VisionAgent, Line, Rectangle, \
    MapObjectGroup


def example_map():
    host = getHostIP()
    app = GUI(id="gui", host=host, run_js=True)

    category = Category(id="map_demo", name="Map Demo", icon="M")
    app.addCategory(category)

    page = Page(id="map_page", name="Map")
    category.addPage(page, position=1)

    # -- Map widget (3m x 3m area) ---------------------------------------------------------
    map_widget = MapWidget(
        widget_id='demo_map',
        limits={"x": [-1, 4], "y": [-1, 4]},
        origin=[0, 0],
        tiles=True,
        tile_size=0.5,
        show_grid=True,
        major_grid_size=1,
        minor_grid_size=0.5,
        initial_display_center=[1.5, 1.5],
        initial_display_zoom=0.85,
    )
    page.addWidget(map_widget, row=1, column=1, width=18, height=18)

    the_map = map_widget.map

    # -- Static objects --------------------------------------------------------------------

    # Some boundary markers
    p1 = Point('corner_a', x=0, y=0, color=[1, 1, 1, 0.6], size=0.04, name='Origin')
    p2 = Point('corner_b', x=3, y=0, color=[1, 1, 1, 0.6], size=0.04, name='(3,0)')
    p3 = Point('corner_c', x=3, y=3, color=[1, 1, 1, 0.6], size=0.04, name='(3,3)')
    p4 = Point('corner_d', x=0, y=3, color=[1, 1, 1, 0.6], size=0.04, name='(0,3)')
    the_map.addObject(p1)
    the_map.addObject(p2)
    the_map.addObject(p3)
    the_map.addObject(p4)

    # Obstacle zone
    obstacle = Rectangle('obstacle', x=1.8, y=0.5, width=0.6, height=0.4,
                          color=[0.8, 0.2, 0.1, 0.4], border_color=[0.8, 0.2, 0.1, 0.8],
                          border_width=2, name='Obstacle')
    the_map.addObject(obstacle)

    # Target zone
    target_zone = Circle('target_zone', x=2.5, y=2.5, radius=0.3,
                          color=[0.1, 0.7, 0.2, 0.15], border_color=[0.1, 0.7, 0.2, 0.5],
                          border_width=2, name='Target')
    the_map.addObject(target_zone)

    # -- Group with waypoints --------------------------------------------------------------
    waypoints_group = MapObjectGroup('waypoints', name='Waypoints')
    the_map.addGroup(waypoints_group)

    wp_positions = [(0.5, 0.5), (1.0, 1.5), (1.5, 2.5), (2.5, 2.5)]
    for i, (wx, wy) in enumerate(wp_positions):
        wp = Point(f'wp{i}', x=wx, y=wy, color=[1, 0.8, 0, 0.8], size=0.035,
                   shape='diamond', name=f'WP{i}', border_width=0)
        waypoints_group.addObject(wp)

    # Lines connecting waypoints
    for i in range(len(wp_positions) - 1):
        wp_a = waypoints_group.objects[f'wp{i}']
        wp_b = waypoints_group.objects[f'wp{i + 1}']
        line = Line(f'path_{i}_{i + 1}', start=wp_a, end=wp_b,
                    color=[1, 0.8, 0, 0.3], width=2, style='dashed', show_name=False)
        waypoints_group.addObject(line)

    # -- Moving agents ---------------------------------------------------------------------
    agent_a = Agent('robot_a', x=0.5, y=0.5, psi=0,
                    color=[0, 0.7, 0.9, 1], size=0.07, name='Robot A')
    the_map.addObject(agent_a)

    agent_b = VisionAgent('robot_b', x=2.0, y=1.0, psi=math.pi / 2,
                          color=[0.9, 0.4, 0.1, 1], size=0.07, name='Robot B',
                          fov=math.pi / 3, vision_radius=0.6)
    the_map.addObject(agent_b)

    # -- Start GUI -------------------------------------------------------------------------
    app.start()

    # -- Animation loop --------------------------------------------------------------------
    t0 = time.time()
    dt = 1 / 20  # 20 Hz updates

    while True:
        t = time.time() - t0

        # Robot A: follows the waypoint path in a loop
        path = wp_positions
        total_len = 0
        segments = []
        for i in range(len(path) - 1):
            dx = path[i + 1][0] - path[i][0]
            dy = path[i + 1][1] - path[i][1]
            seg_len = math.hypot(dx, dy)
            segments.append((path[i], path[i + 1], seg_len))
            total_len += seg_len

        speed = 0.3  # m/s
        cycle_time = total_len / speed
        progress = (t * speed) % total_len

        acc = 0
        ax, ay, apsi = 0, 0, 0
        for (sx, sy), (ex, ey), seg_len in segments:
            if acc + seg_len >= progress:
                frac = (progress - acc) / seg_len
                ax = sx + frac * (ex - sx)
                ay = sy + frac * (ey - sy)
                apsi = math.atan2(ey - sy, ex - sx)
                break
            acc += seg_len

        agent_a.update({'x': ax, 'y': ay, 'psi': apsi})

        # Robot B: orbits around center of map
        cx, cy = 1.5, 1.5
        orbit_r = 1.0
        omega = 0.4  # rad/s
        bx = cx + orbit_r * math.cos(omega * t)
        by = cy + orbit_r * math.sin(omega * t)
        bpsi = omega * t + math.pi / 2  # tangent direction
        agent_b.update({'x': bx, 'y': by, 'psi': bpsi})

        time.sleep(dt)


if __name__ == '__main__':
    example_map()
