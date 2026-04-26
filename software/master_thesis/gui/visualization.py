from __future__ import annotations

from typing import TYPE_CHECKING

from extensions.babylon.src.lib.objects.drawings import CircleDrawing, LineDrawing

from master_thesis.gui.containers import RobotGUIContainer

if TYPE_CHECKING:
    from master_thesis.gui.thesis_gui import ThesisGUI


def toggle_action_grid(gui: ThesisGUI) -> None:
    """Toggle display of the discretized subgoal action-space grid as dots."""
    if gui._action_grid_dots:
        for dot in gui._action_grid_dots:
            try:
                gui.babylon_visualization.removeObject(dot)
            except Exception:
                pass
        gui._action_grid_dots.clear()
        gui.logger.info("Action grid hidden")
        return

    scenario = gui._last_scenario
    if scenario is None:
        gui.logger.warning("Load a scenario first")
        return

    gap_geo = getattr(scenario, 'gap_geometry', None)
    if gap_geo is None:
        gui.logger.warning("Scenario has no gap_geometry — cannot build action grid")
        return

    from master_thesis.modules.subgoal_predictor.train_subgoal import build_free_positions
    positions = build_free_positions(gui.sim, gap_geo, grid_stride=0.15,
                                     subgoal_limits=getattr(scenario, 'subgoal_limits', None))

    for x, y in positions:
        dot = CircleDrawing(
            f"agrid_{len(gui._action_grid_dots)}",
            x=float(x), y=float(y),
            radius=0.025,
            fill_color=[0.95, 0.75, 0.1, 0.85],
            border_color=[1.0, 0.9, 0.2, 1.0],
            border_width=0.005,
        )
        try:
            gui.babylon_visualization.addObject(dot)
        except ValueError:
            pass
        gui._action_grid_dots.append(dot)

    gui.logger.info(f"Action grid shown: {len(gui._action_grid_dots)} positions")


def show_trajectories(gui: ThesisGUI) -> None:
    """Visualize planned paths / subgoals for all agents."""
    for robot in gui.robots.values():
        show_trajectory_for_robot(gui, robot)

    gui.logger.info(f"Trajectories shown for {len(gui.robots)} agents")


def show_trajectory_for_robot(gui: ThesisGUI, robot: RobotGUIContainer) -> None:
    """Draw trajectory lines for a single robot.

    For efficiency, reuses existing LineDrawing objects via setEndpoints()
    instead of removing/adding babylon objects each refresh.
    """
    agent = robot.sim_agent
    plan_result = agent.sgm.last_plan_result
    if plan_result is None:
        return

    # Determine task color for the lines
    assigned = agent.assigned_task
    task_color = [1, 1, 1]
    if assigned is not None:
        task_gui = gui.tasks.get(assigned.object_id)
        if task_gui and task_gui.babylon is not None:
            task_color = task_gui.babylon.config.get('color', [1, 1, 1])

    line_color = [*task_color[:3], 0.7]
    agent_id = agent.agent_id

    # Collect segments: list of (start_xy, end_xy)
    segments: list[tuple[list, list]] = []

    if plan_result.phase_container is not None:
        # OMPL trajectory: subsample to at most MAX_TRAJ_SEGMENTS line segments.
        # The smooth planner produces one state per Ts tick (potentially 200+),
        # which would create hundreds of Babylon objects and stall rendering.
        MAX_TRAJ_SEGMENTS = 30
        states = plan_result.phase_container.states
        if states is not None and len(states) >= 2:
            step = max(1, (len(states) - 1) // MAX_TRAJ_SEGMENTS)
            indices = list(range(0, len(states), step))
            if indices[-1] != len(states) - 1:
                indices.append(len(states) - 1)
            for j in range(len(indices) - 1):
                s0, s1 = states[indices[j]], states[indices[j + 1]]
                segments.append(([float(s0[0]), float(s0[1])],
                                 [float(s1[0]), float(s1[1])]))
        style = 'solid'

    elif plan_result.subgoal is not None:
        # Reactive / RL: MPPI rollout, subsampled to ~10 segments
        mppi_traj = getattr(agent.executor, 'last_trajectory', None)
        if mppi_traj is not None and len(mppi_traj) >= 2:
            step = max(1, len(mppi_traj) // 10)
            indices = list(range(0, len(mppi_traj), step))
            if indices[-1] != len(mppi_traj) - 1:
                indices.append(len(mppi_traj) - 1)
            for j in range(len(indices) - 1):
                s0, s1 = mppi_traj[indices[j]], mppi_traj[indices[j + 1]]
                segments.append(([float(s0[0]), float(s0[1])],
                                 [float(s1[0]), float(s1[1])]))
        style = 'dashed'
    else:
        return

    # Reuse existing lines where possible, add/remove only the difference
    existing = robot.trajectory_lines
    needed = len(segments)

    # Remove excess lines
    while len(existing) > needed:
        try:
            gui.babylon_visualization.removeObject(existing.pop())
        except Exception:
            pass

    # Update existing lines in-place
    for i, (start, end) in enumerate(segments[:len(existing)]):
        existing[i].setEndpoints(start, end)

    # Create new lines for any additional segments
    for i in range(len(existing), needed):
        start, end = segments[i]
        line = LineDrawing(
            f"traj_{agent_id}_{i}",
            start=start, end=end,
            color=line_color, width=0.015, style=style,
        )
        try:
            gui.babylon_visualization.addObject(line)
        except ValueError:
            try:
                gui.babylon_visualization.removeObject(line)
            except Exception:
                pass
            gui.babylon_visualization.addObject(line)
        existing.append(line)

    # Draw subgoal markers (remaining RL-predicted subgoals not yet visited)
    sgm = agent.sgm
    pending_subgoals = sgm._subgoal_queue[sgm._subgoal_idx:]
    existing_markers = robot.subgoal_markers
    needed_markers = len(pending_subgoals)

    # Remove excess markers
    while len(existing_markers) > needed_markers:
        try:
            gui.babylon_visualization.removeObject(existing_markers.pop())
        except Exception:
            pass

    # Update existing markers or add new ones
    for i, sg in enumerate(pending_subgoals):
        x, y = float(sg[0]), float(sg[1])
        if i < len(existing_markers):
            existing_markers[i].setPosition(x, y)
        else:
            marker = CircleDrawing(
                f"sg_{agent_id}_{i}",
                x=x, y=y,
                radius=0.06,
                fill_color=[*task_color[:3], 0.8],
                border_color=[*task_color[:3], 1.0],
                border_width=0.01,
            )
            try:
                gui.babylon_visualization.addObject(marker)
            except ValueError:
                try:
                    gui.babylon_visualization.removeObject(marker)
                except Exception:
                    pass
                gui.babylon_visualization.addObject(marker)
            existing_markers.append(marker)

    # Draw geometric waypoints (after RDP+LOS simplification, before Bézier)
    raw_waypoints = plan_result.waypoints or []
    existing_wp = robot.waypoint_markers
    needed_wp = len(raw_waypoints)

    while len(existing_wp) > needed_wp:
        try:
            gui.babylon_visualization.removeObject(existing_wp.pop())
        except Exception:
            pass

    for i, wp in enumerate(raw_waypoints):
        x, y = float(wp[0]), float(wp[1])
        if i < len(existing_wp):
            existing_wp[i].setPosition(x, y)
        else:
            wp_marker = CircleDrawing(
                f"wp_{agent_id}_{i}",
                x=x, y=y,
                radius=0.03,
                fill_color=[*task_color[:3], 0.9],
                border_color=[*task_color[:3], 1.0],
                border_width=0.006,
            )
            try:
                gui.babylon_visualization.addObject(wp_marker)
            except ValueError:
                try:
                    gui.babylon_visualization.removeObject(wp_marker)
                except Exception:
                    pass
                gui.babylon_visualization.addObject(wp_marker)
            existing_wp.append(wp_marker)


def clear_visualization_overlays(gui: ThesisGUI) -> None:
    """Remove all assignment circles and trajectory lines from Babylon."""
    for robot in gui.robots.values():
        if robot.assignment_circle is not None:
            try:
                gui.babylon_visualization.removeObject(robot.assignment_circle)
            except Exception:
                pass
            robot.assignment_circle = None
        for line in robot.trajectory_lines:
            try:
                gui.babylon_visualization.removeObject(line)
            except Exception:
                pass
        robot.trajectory_lines.clear()
        for marker in robot.subgoal_markers:
            try:
                gui.babylon_visualization.removeObject(marker)
            except Exception:
                pass
        robot.subgoal_markers.clear()
        for marker in robot.waypoint_markers:
            try:
                gui.babylon_visualization.removeObject(marker)
            except Exception:
                pass
        robot.waypoint_markers.clear()
        robot._last_plan_result = None
