from __future__ import annotations

from typing import TYPE_CHECKING

from extensions.babylon.src.lib.objects.drawings import CircleDrawing, LineDrawing

from master_thesis.gui.containers import RobotGUIContainer

if TYPE_CHECKING:
    from master_thesis.gui.thesis_gui import ThesisGUI
    from master_thesis.universal.universal_agent import FRODOUniversalAgent


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_task_color(gui: ThesisGUI, agent: FRODOUniversalAgent) -> list:
    """Return the RGB color of the agent's currently-assigned task, or white."""
    assigned = agent.assigned_task
    if assigned is not None:
        task_gui = gui.tasks.get(assigned.object_id)
        if task_gui and task_gui.babylon is not None:
            return task_gui.babylon.config.get('color', [1, 1, 1])
    return [1, 1, 1]


def _add_babylon_object(gui: ThesisGUI, obj) -> None:
    """Add a Babylon object, removing a stale duplicate first if needed."""
    try:
        gui.babylon_visualization.addObject(obj)
    except ValueError:
        try:
            gui.babylon_visualization.removeObject(obj)
        except Exception:
            pass
        gui.babylon_visualization.addObject(obj)


# ---------------------------------------------------------------------------
# Public visualization functions
# ---------------------------------------------------------------------------


def toggle_action_grid(gui: ThesisGUI) -> None:
    """Removed: the subgoal action space is now fully continuous — no discrete grid exists."""
    gui.logger.info("Action grid display is no longer available (continuous action space)")


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
    task_color = _get_task_color(gui, agent)
    line_color = [*task_color[:3], 0.7]
    agent_id = agent.agent_id

    # Collect segments: list of (start_xy, end_xy)
    segments: list[tuple[list, list]] = []

    if plan_result.phase_container is not None:
        # OMPL trajectory: subsample to at most MAX_TRAJ_SEGMENTS line segments.
        # The smooth planner produces one state per Ts tick (potentially 200+),
        # which would create hundreds of Babylon objects and stall rendering.
        MAX_TRAJ_SEGMENTS = 30

        def _append_states(states_list: list, budget: int) -> None:
            if states_list is None or len(states_list) < 2:
                return
            step = max(1, (len(states_list) - 1) // budget)
            indices = list(range(0, len(states_list), step))
            if indices[-1] != len(states_list) - 1:
                indices.append(len(states_list) - 1)
            for j in range(len(indices) - 1):
                s0, s1 = states_list[indices[j]], states_list[indices[j + 1]]
                segments.append(([float(s0[0]), float(s0[1])],
                                 [float(s1[0]), float(s1[1])]))

        _append_states(plan_result.phase_container.states, MAX_TRAJ_SEGMENTS)

        # When _show_full_trajectory is set (e.g. for pre-execution screenshots),
        # also draw the pre-planned remaining segments (subgoal → goal, etc.).
        if getattr(gui, '_show_full_trajectory', False):
            for pre_result in agent.sgm._pre_planned_results:
                if pre_result.phase_container is not None:
                    _append_states(pre_result.phase_container.states, MAX_TRAJ_SEGMENTS)

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
        _add_babylon_object(gui, line)
        existing.append(line)

    # Draw subgoal markers (remaining RL-predicted subgoals not yet visited)
    _update_subgoal_markers(gui, robot, task_color)

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


def _update_subgoal_markers(gui: ThesisGUI, robot: RobotGUIContainer,
                             task_color: list) -> None:
    """Sync the Babylon subgoal-marker circles for *robot* to the current SGM queue.

    Reuses existing CircleDrawing objects where possible to avoid churn.
    ``task_color`` is the RGB list (len >= 3) for the agent's assigned task.
    """
    agent = robot.sim_agent
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
                f"sg_{agent.agent_id}_{i}",
                x=x, y=y,
                radius=0.06,
                fill_color=[*task_color[:3], 0.8],
                border_color=[*task_color[:3], 1.0],
                border_width=0.01,
            )
            _add_babylon_object(gui, marker)
            existing_markers.append(marker)


def refresh_assignment_circles(gui: ThesisGUI) -> None:
    """Immediately create Babylon assignment circles for all assigned agents.

    Mirrors the lazy circle-creation in ``_simulationOutputStep()`` but can be
    called imperatively — e.g. right after ``sim.start_ta()`` — without waiting
    for the next simulation tick.
    """
    created = 0
    for robot in gui.robots.values():
        if robot.assignment_circle is not None:
            continue  # already shown
        agent = robot.sim_agent
        assigned = agent.assigned_task
        if assigned is None:
            continue
        task_gui = gui.tasks.get(assigned.object_id)
        if task_gui is None or task_gui.babylon is None:
            continue
        color = task_gui.babylon.config.get('color', [1, 1, 1])
        state = agent.state
        circle = CircleDrawing(
            f"assign_{agent.agent_id}",
            x=float(state.x), y=float(state.y),
            radius=0.125,
            fill_color=[*color[:3], 0.25],
            border_color=[*color[:3], 0.9],
            border_width=0.015,
        )
        _add_babylon_object(gui, circle)
        robot.assignment_circle = circle
        robot._last_assigned_task_id = assigned.object_id
        created += 1

    if created:
        gui.logger.info(f"Assignment circles created for {created} agent(s)")


def show_subgoal_markers(gui: ThesisGUI) -> None:
    """Draw subgoal markers for all agents from their SGM queue.

    Works even before motion planning has been run (does not require
    ``plan_result`` to be set).  Intended for the 'predict subgoals only'
    step in the staged GUI workflow.
    """
    shown = 0
    for robot in gui.robots.values():
        agent = robot.sim_agent
        sgm = agent.sgm
        if not sgm._subgoal_queue:
            continue
        task_color = _get_task_color(gui, agent)
        _update_subgoal_markers(gui, robot, task_color)
        shown += len(sgm._subgoal_queue[sgm._subgoal_idx:])

    gui.logger.info(f"Subgoal markers shown: {shown} total across {len(gui.robots)} agent(s)")


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
