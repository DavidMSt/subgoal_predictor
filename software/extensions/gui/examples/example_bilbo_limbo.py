import math
import time

from core.utils.network.network import getHostIP
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.bilbo_limbo import BilboLimboWidget, LimboBilboConfig


def main():
    host = getHostIP()
    app = GUI(id="gui", host=host, run_js=True)

    category = Category(id="limbo", name="Limbo", icon="L")
    app.addCategory(category)

    # ==========================================================================
    # Page 1: Limbo scene — wide widget with robot ducking under a bar
    # ==========================================================================
    page1 = Page(id="limbo", name="Limbo Bar")
    category.addPage(page1, position=1)

    limbo = BilboLimboWidget(
        widget_id='limbo_scene',
        x_range=[-0.8, 0.8],
        show_grid=True,
        grid_spacing=0.1,
    )
    page1.addWidget(limbo, row=1, column=1, width=50, height=10)

    # ==========================================================================
    # Page 2: Multiple robots side by side — three different widget sizes
    # ==========================================================================
    page2 = Page(id="multi", name="Multi-Robot")
    category.addPage(page2, position=2)

    # Small square widget — single robot, no grid
    small = BilboLimboWidget(
        widget_id='small_view',
        x_range=[-0.2, 0.2],
        background_color=[0.12, 0.12, 0.18],
    )
    page2.addWidget(small, row=1, column=1, width=12, height=9)

    # Medium widget — two robots, grid on
    medium = BilboLimboWidget(
        widget_id='medium_view',
        x_range=[-0.5, 0.5],
        show_grid=True,
        grid_spacing=0.05,
        background_color=[0.1, 0.14, 0.2],
    )
    page2.addWidget(medium, row=1, column=13, width=20, height=9)

    # Tall narrow widget — one robot with obstacles stacked vertically
    tall = BilboLimboWidget(
        widget_id='tall_view',
        x_range=[-0.25, 0.25],
        show_grid=True,
        grid_spacing=0.05,
        background_color=[0.15, 0.1, 0.15],
    )
    page2.addWidget(tall, row=1, column=33, width=10, height=18)

    # Wide bottom strip — obstacle course
    course = BilboLimboWidget(
        widget_id='course_view',
        x_range=[-1.5, 1.5],
        show_grid=True,
        grid_spacing=0.2,
        floor_color=[0.75, 0.75, 0.7],
        floor_edge_color=[0.3, 0.3, 0.25],
        background_color=[0.18, 0.18, 0.22],
    )
    page2.addWidget(course, row=10, column=1, width=32, height=9)

    # ==========================================================================
    # Page 3: Showcase — dynamic scene with trajectories and labels
    # ==========================================================================
    page3 = Page(id="showcase", name="Dynamic Scene")
    category.addPage(page3, position=3)

    dynamic = BilboLimboWidget(
        widget_id='dynamic_view',
        x_range=[-1.0, 1.0],
        show_grid=True,
        grid_spacing=0.1,
    )
    page3.addWidget(dynamic, row=1, column=1, width=50, height=14)

    # ------------------------------------------------------------------
    app.start()
    # ------------------------------------------------------------------

    # ======================================================================
    # Populate Page 1: Limbo bar scene
    # ======================================================================
    limbo.add_bilbo('robot', config=LimboBilboConfig(
        body_color=[0.3, 0.5, 0.9],
    ), state={'x': -0.5, 'theta': 0.0})

    # Limbo bar with two support posts
    bar_y = 0.18
    limbo.add_rectangle('post_l', x=-0.22, y=0.0, width=0.015, height=bar_y,
                        color=[0.55, 0.55, 0.55], edge_color=[0.3, 0.3, 0.3])
    limbo.add_rectangle('post_r', x=0.205, y=0.0, width=0.015, height=bar_y,
                        color=[0.55, 0.55, 0.55], edge_color=[0.3, 0.3, 0.3])
    limbo.add_rectangle('bar', x=-0.22, y=bar_y, width=0.44, height=0.015,
                        color=[0.95, 0.8, 0.15], edge_color=[0.7, 0.55, 0.05],
                        edge_width=1.5)

    # Labels on the limbo scene
    limbo.set_label('left', 'Limbo Bar', color=[1, 1, 1], font_size=16, font_weight='bold')
    limbo.set_label('right', 'h = 0.18 m', color=[0.9, 0.8, 0.2], font_size=13)

    # Reference trajectory: the path the robot center should follow
    ref_xs = [round(-0.5 + i * 0.01, 3) for i in range(116)]
    ref_ys = [round(0.06, 3)] * len(ref_xs)  # wheel center height
    limbo.add_path('ref_path', x=ref_xs, y=ref_ys,
                   color=[0.5, 0.5, 0.5], width=1.5, dash=[6, 4], opacity=0.5)

    # ======================================================================
    # Populate Page 2: Multi-robot
    # ======================================================================

    # Small: single centered robot
    small.add_bilbo('solo', config=LimboBilboConfig(
        body_color=[0.9, 0.35, 0.25],
    ), state={'x': 0.0, 'theta': 0.0})
    small.set_label('left', 'Solo', color=[0.9, 0.35, 0.25], font_size=11, font_weight='bold')

    # Medium: two robots with a circle obstacle between them
    medium.add_bilbo('blue', config=LimboBilboConfig(
        body_color=[0.25, 0.45, 0.85],
    ), state={'x': -0.2, 'theta': 0.0})
    medium.add_bilbo('green', config=LimboBilboConfig(
        body_color=[0.2, 0.75, 0.35],
    ), state={'x': 0.2, 'theta': 0.0})
    medium.add_circle('ball', x=0.0, y=0.1, radius=0.035,
                      color=[0.9, 0.5, 0.1], edge_color=[0.6, 0.3, 0.05])
    medium.set_label('left', 'Dual', color=[1, 1, 1], font_size=11, font_weight='bold')

    # Tall: one robot with stacked horizontal bars at different heights
    tall.add_bilbo('climber', config=LimboBilboConfig(
        body_color=[0.7, 0.3, 0.8],
    ), state={'x': 0.0, 'theta': 0.0})
    for i, h in enumerate([0.08, 0.16, 0.24]):
        w = 0.18 - i * 0.04
        tall.add_rectangle(f'bar_{i}', x=-w / 2, y=h, width=w, height=0.012,
                           color=[0.4 + i * 0.2, 0.4 + i * 0.15, 0.2],
                           edge_color=[0.3, 0.3, 0.2])

    # Course: obstacle course with three robots and mixed obstacles
    course.add_bilbo('r1', config=LimboBilboConfig(
        body_color=[0.85, 0.25, 0.25],
    ), state={'x': -1.0, 'theta': 0.0})
    course.add_bilbo('r2', config=LimboBilboConfig(
        body_color=[0.25, 0.7, 0.25],
    ), state={'x': 0.0, 'theta': 0.0})
    course.add_bilbo('r3', config=LimboBilboConfig(
        body_color=[0.25, 0.4, 0.9],
    ), state={'x': 1.0, 'theta': 0.0})
    # Walls
    course.add_rectangle('wall1', x=-0.52, y=0.0, width=0.03, height=0.22,
                         color=[0.5, 0.5, 0.55], edge_color=[0.3, 0.3, 0.3])
    course.add_rectangle('wall2', x=0.49, y=0.0, width=0.03, height=0.22,
                         color=[0.5, 0.5, 0.55], edge_color=[0.3, 0.3, 0.3])
    # Low bar
    course.add_rectangle('low_bar', x=-0.52, y=0.15, width=1.04, height=0.012,
                         color=[0.9, 0.7, 0.1], edge_color=[0.6, 0.4, 0.05])
    # Circles as bumps
    for i, cx in enumerate([-0.8, -0.3, 0.25, 0.75]):
        course.add_circle(f'bump_{i}', x=cx, y=0.04, radius=0.04,
                          color=[0.6, 0.35, 0.15, 0.8], edge_color=[0.4, 0.2, 0.1])
    course.set_label('left', 'Course', color=[1, 1, 1], font_size=12, font_weight='bold')
    course.set_label('right', '3 robots', color=[0.7, 0.7, 0.7], font_size=11)

    # ======================================================================
    # Populate Page 3: Dynamic scene with trajectory and labels
    # ======================================================================
    dynamic.add_bilbo('main', config=LimboBilboConfig(
        body_color=[0.3, 0.6, 0.9],
    ), state={'x': 0.0, 'theta': 0.0})

    # Static reference path (dashed)
    ref_xs_d = [round(-0.8 + i * 0.016, 3) for i in range(101)]
    ref_ys_d = [round(0.06, 3)] * len(ref_xs_d)
    dynamic.add_path('ref', x=ref_xs_d, y=ref_ys_d,
                     color=[0.4, 0.4, 0.5], width=1.5, dash=[6, 4], opacity=0.4)

    # Live trajectory (will be updated dynamically with gradient)
    dynamic.add_path('trail', x=[], y=[],
                     gradient=True,
                     gradient_start_color=[0.2, 0.4, 0.8, 0.1],
                     gradient_end_color=[0.3, 0.9, 1.0, 1.0],
                     width=2.5)

    dynamic.set_label('left', 'Dynamic Scene', color=[1, 1, 1], font_size=16, font_weight='bold')

    # ======================================================================
    # Animation loop — drives all scenes simultaneously
    # ======================================================================
    t0 = time.time()
    next_obstacle_time = 3.0
    obstacle_idx = 0
    dynamic_obstacles = []
    trail_x = []
    trail_y = []
    trail_max_len = 200

    while True:
        t = time.time() - t0

        # --- Page 1: Limbo ---
        # Robot drives left-to-right and leans forward to pass under the bar
        limbo_x = -0.5 + 0.65 * (0.5 + 0.5 * math.sin(0.35 * t - math.pi / 2))
        # Lean peaks as robot passes under bar center (x ~ 0)
        dist_to_bar = abs(limbo_x)
        lean = 0.4 * math.exp(-(dist_to_bar / 0.15) ** 2) * math.copysign(1, math.cos(0.35 * t))
        limbo.update_bilbo('robot', x=limbo_x, theta=lean)

        # Update limbo trail — actual wheel center path
        limbo_trail_x = trail_x[-100:] + [limbo_x]
        limbo_trail_y = [0.06] * len(limbo_trail_x)
        limbo.update_path('ref_path', x=limbo_trail_x, y=limbo_trail_y)

        # --- Page 2: Small — gentle rocking ---
        small.update_bilbo('solo', theta=0.2 * math.sin(1.5 * t))

        # --- Page 2: Medium — two robots swaying, approaching/retreating ---
        medium.update_bilbo('blue', x=-0.2 + 0.08 * math.sin(0.6 * t),
                            theta=0.15 * math.sin(1.0 * t))
        medium.update_bilbo('green', x=0.2 - 0.08 * math.sin(0.6 * t),
                            theta=-0.15 * math.sin(1.0 * t))

        # --- Page 2: Tall — robot oscillates theta dramatically ---
        tall.update_bilbo('climber', theta=0.5 * math.sin(0.8 * t))

        # --- Page 2: Course — three robots driving independently ---
        course.update_bilbo('r1', x=-1.0 + 0.4 * math.sin(0.5 * t),
                            theta=0.2 * math.sin(0.5 * t))
        course.update_bilbo('r2', x=0.3 * math.sin(0.3 * t),
                            theta=0.25 * math.sin(0.7 * t))
        course.update_bilbo('r3', x=1.0 - 0.4 * math.sin(0.4 * t + 1),
                            theta=-0.2 * math.sin(0.6 * t))

        # --- Page 3: Dynamic scene ---
        # Robot figure-eight motion
        main_x = 0.5 * math.sin(0.4 * t)
        main_y_offset = 0.06 + 0.03 * math.sin(0.8 * t)
        dynamic.update_bilbo('main', x=main_x, theta=0.3 * math.sin(0.8 * t))

        # Append to trail and update path
        trail_x.append(main_x)
        trail_y.append(main_y_offset)
        if len(trail_x) > trail_max_len:
            trail_x = trail_x[-trail_max_len:]
            trail_y = trail_y[-trail_max_len:]
        dynamic.update_path('trail', x=trail_x, y=trail_y)

        # Update right label with live info
        dynamic.set_label('right', f'x = {main_x:+.2f} m',
                          color=[0.6, 0.9, 1.0], font_size=13, font_family='monospace')

        # Periodically add/remove obstacles
        if t >= next_obstacle_time:
            # Remove oldest if too many
            if len(dynamic_obstacles) >= 5:
                old_id = dynamic_obstacles.pop(0)
                dynamic.remove_rectangle(old_id)

            # Add a new obstacle at a random-ish position
            oid = f'obs_{obstacle_idx}'
            ox = 0.7 * math.sin(obstacle_idx * 1.7)
            oy = 0.05 + 0.12 * abs(math.sin(obstacle_idx * 0.9))
            r = (0.3 + 0.5 * abs(math.sin(obstacle_idx * 2.3)))
            g = (0.3 + 0.5 * abs(math.sin(obstacle_idx * 1.1)))
            b = (0.3 + 0.5 * abs(math.sin(obstacle_idx * 3.7)))
            dynamic.add_rectangle(oid, x=ox - 0.06, y=oy, width=0.12, height=0.015,
                                  color=[r, g, b, 0.9], edge_color=[r * 0.5, g * 0.5, b * 0.5])
            dynamic_obstacles.append(oid)
            obstacle_idx += 1
            next_obstacle_time = t + 2.5

        # Toggle grid every 15 seconds on the dynamic widget
        dynamic.set_grid(show=(int(t / 15) % 2 == 0))

        time.sleep(0.05)


if __name__ == '__main__':
    main()
