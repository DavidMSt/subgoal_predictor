import numpy as np

def maze_single_2x2(demo):
    """
    Setup a simple maze scenario.
    Can be called from thesis_demo without circular imports.

    Args:
        demo: ThesisDemo instance
    """
    demo.sim.environment.set_limits(limits = ((-1, 1), (-1, 1)))

    wall_thickness = 0.1

    # Add robot at start position (bottom-left area)
    r = demo.newRobot("frodo1")
    r.sim_agent.state.x = -0.75
    r.sim_agent.state.y = -0.75
    r.sim_agent.state.psi = 0.0

    # Create 2m x 2m maze walls (thickness 0.1m)
    # Note: length is along x-axis (horizontal), width is thickness
    # Vertical walls are rotated by psi=pi/2

    # Outer boundary walls (horizontal walls)
    demo.newObstacle("wall_top", x=0.0, y=1.0, length=2.0, width=wall_thickness)
    demo.newObstacle("wall_bottom", x=0.0, y=-1.0, length=2.0, width=wall_thickness)
    # Outer boundary walls (vertical walls - rotated)
    demo.newObstacle("wall_left", x=-1.0, y=0.0, length=2.0, width=wall_thickness, psi=np.pi/2)
    demo.newObstacle("wall_right", x=1.0, y=0.0, length=2.0, width=wall_thickness, psi=np.pi/2)

    # Internal maze walls (traced from the image)
    # Top-left vertical segment
    demo.newObstacle("maze_1", x=-0.5, y=0.5, length=0.5, width=wall_thickness, psi=np.pi/2)

    # Top-left horizontal segment
    demo.newObstacle("maze_2", x=-0.25, y=0.5, length=0.5, width=wall_thickness)

    # Top-center vertical segment
    demo.newObstacle("maze_3", x=0.0, y=0.25, length=0.5, width=wall_thickness, psi=np.pi/2)

    # Top-right horizontal segment
    demo.newObstacle("maze_4", x=0.5, y=0.5, length=0.5, width=wall_thickness)

    # Middle-left vertical segment
    demo.newObstacle("maze_5", x=-0.5, y=-0.25, length=0.5, width=wall_thickness, psi=np.pi/2)

    # Middle-center horizontal segment
    demo.newObstacle("maze_6", x=0.0, y=0.0, length=0.5, width=wall_thickness)

    # Middle-right vertical segment
    demo.newObstacle("maze_7", x=0.5, y=-0.25, length=0.5, width=wall_thickness, psi=np.pi/2)

    # Bottom-left horizontal segment
    demo.newObstacle("maze_8", x=-0.25, y=-0.5, length=0.5, width=wall_thickness)

    # Bottom-center vertical segment
    demo.newObstacle("maze_9", x=0.0, y=-0.75, length=0.5, width=wall_thickness, psi=np.pi/2)

    # Bottom-right horizontal segment
    demo.newObstacle("maze_10", x=0.5, y=-0.5, length=0.5, width=wall_thickness)

    # Add goal task (top-right area)
    demo.newTask("goal1", x=0.75, y=0.75, color=[0, 1, 0])

    demo.logger.info("Simple maze setup complete. 2m x 2m maze with 0.1m wall thickness")


def maze_single_3x3_three_agents(demo):
    """Setup a 3m x 3m maze scenario with three agents.

    All positions and wall lengths are snapped to a 0.25m grid.

    Args:
        demo: ThesisDemo instance
    """
    GRID = 0.1
    wall_thickness = GRID  # grid-aligned thickness so wall faces align with the grid
    half = 1.5  # 3m / 2
    half_in = half - wall_thickness / 2  # place boundary walls inside the 3x3 extent

    def snap(v: float) -> float:
        # Deterministic snap to nearest GRID multiple
        return float(np.round(v / GRID) * GRID)

    def add_obstacle(oid: str, *, x: float, y: float, length: float, width: float, psi: float = 0.0):
        demo.newObstacle(
            oid,
            x=snap(x),
            y=snap(y),
            length=snap(length),
            width=snap(width),
            psi=psi,
        )

    def add_task(tid: str, *, x: float, y: float, color=None):
        if color is None:
            demo.newTask(tid, x=snap(x), y=snap(y))
        else:
            demo.newTask(tid, x=snap(x), y=snap(y), color=color)

    # ──────────────────────────────────
    # Agents (three separate ones)
    # ──────────────────────────────────
    r1 = demo.newRobot("frodo1")
    r1.sim_agent.state.x = snap(-1.25)
    r1.sim_agent.state.y = snap(-1.25)
    r1.sim_agent.state.psi = 0.0

    r2 = demo.newRobot("frodo2")
    r2.sim_agent.state.x = snap(1.25)
    r2.sim_agent.state.y = snap(-1.25)
    r2.sim_agent.state.psi = np.pi

    r3 = demo.newRobot("frodo3")
    r3.sim_agent.state.x = snap(-1.25)
    r3.sim_agent.state.y = snap(1.25)
    r3.sim_agent.state.psi = -np.pi / 2

    # ──────────────────────────────────
    # Outer boundary (3m x 3m)
    # ──────────────────────────────────
    add_obstacle("wall_top", x=0.0, y=half_in, length=3.0, width=wall_thickness)
    add_obstacle("wall_bottom", x=0.0, y=-half_in, length=3.0, width=wall_thickness)
    add_obstacle("wall_left", x=-half_in, y=0.0, length=3.0, width=wall_thickness, psi=np.pi / 2)
    add_obstacle("wall_right", x=half_in, y=0.0, length=3.0, width=wall_thickness, psi=np.pi / 2)

    # ──────────────────────────────────
    # Internal maze walls (grid-aligned; all centers/lengths snapped)
    # ──────────────────────────────────

    # Top row
    add_obstacle("m1", x=-0.75, y=1.0, length=0.75, width=wall_thickness)
    add_obstacle("m2", x=0.75, y=1.0, length=0.75, width=wall_thickness)

    add_obstacle("m3", x=-0.5, y=0.75, length=0.75, width=wall_thickness, psi=np.pi / 2)
    add_obstacle("m4", x=0.5, y=0.75, length=0.75, width=wall_thickness, psi=np.pi / 2)

    # Middle structure
    add_obstacle("m5", x=0.0, y=0.25, length=1.0, width=wall_thickness)
    add_obstacle("m6", x=-1.0, y=0.0, length=1.0, width=wall_thickness, psi=np.pi / 2)
    add_obstacle("m7", x=1.0, y=0.0, length=1.0, width=wall_thickness, psi=np.pi / 2)

    add_obstacle("m8", x=-0.5, y=-0.25, length=0.75, width=wall_thickness)
    add_obstacle("m9", x=0.5, y=-0.25, length=0.75, width=wall_thickness)

    # Bottom row
    add_obstacle("m10", x=-0.75, y=-1.0, length=0.75, width=wall_thickness)
    add_obstacle("m11", x=0.75, y=-1.0, length=0.75, width=wall_thickness)

    add_obstacle("m12", x=0.0, y=-0.75, length=0.75, width=wall_thickness, psi=np.pi / 2)

    # ──────────────────────────────────
    # Goals / tasks
    # ──────────────────────────────────
    add_task("goal1", x=1.25, y=1.25, color=[0, 1, 0])
    add_task("goal2", x=-1.25, y=0.0, color=[0, 0, 1])
    add_task("goal3", x=0.0, y=-1.25, color=[1, 0, 0])

    demo.logger.info("3x3 maze setup complete (0.25m grid-snapped), with three agents")
