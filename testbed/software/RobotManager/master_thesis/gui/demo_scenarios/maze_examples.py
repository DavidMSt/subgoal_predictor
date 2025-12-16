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


def maze_multi_4x4(demo):
    """
    Setup a larger 4x4 meter maze scenario with three agents.
    Can be called from thesis_demo without circular imports.

    Args:
        demo: ThesisDemo instance
    """
    demo.sim.environment.set_limits(limits=((-2, 2), (-2, 2)))

    wall_thickness = 0.1

    # Add three robots at different start positions (in clear spaces)
    r1 = demo.newRobot("frodo1")
    r1.sim_agent.state.x = -1.75
    r1.sim_agent.state.y = -1.75
    r1.sim_agent.state.psi = 0.0

    r2 = demo.newRobot("frodo2")
    r2.sim_agent.state.x = -1.75
    r2.sim_agent.state.y = 1.75
    r2.sim_agent.state.psi = 0.0

    r3 = demo.newRobot("frodo3")
    r3.sim_agent.state.x = 1.75
    r3.sim_agent.state.y = -1.75
    r3.sim_agent.state.psi = 0.0

    # Create 4m x 4m maze walls (thickness 0.1m)
    # Note: length is along x-axis (horizontal), width is thickness
    # Vertical walls are rotated by psi=pi/2
    # Minimum opening: 0.5m between walls for robot passage

    # Outer boundary walls
    demo.newObstacle("wall_top", x=0.0, y=2.0, length=4.0, width=wall_thickness)
    demo.newObstacle("wall_bottom", x=0.0, y=-2.0, length=4.0, width=wall_thickness)
    demo.newObstacle("wall_left", x=-2.0, y=0.0, length=4.0, width=wall_thickness, psi=np.pi/2)
    demo.newObstacle("wall_right", x=2.0, y=0.0, length=4.0, width=wall_thickness, psi=np.pi/2)

    # Internal maze walls with proper spacing (min 0.5m openings)
    # Walls are 1.0m long with 0.5m gaps, creating a grid-like maze

    # Top row (y = 1.5)
    demo.newObstacle("maze_1", x=-1.25, y=1.5, length=1.0, width=wall_thickness, psi=np.pi/2)
    demo.newObstacle("maze_2", x=0.0, y=1.5, length=1.0, width=wall_thickness)
    demo.newObstacle("maze_3", x=1.25, y=1.5, length=1.0, width=wall_thickness, psi=np.pi/2)

    # Upper-middle row (y = 0.75)
    demo.newObstacle("maze_4", x=-1.5, y=0.75, length=0.5, width=wall_thickness)
    demo.newObstacle("maze_5", x=-0.5, y=0.75, length=1.0, width=wall_thickness, psi=np.pi/2)
    demo.newObstacle("maze_6", x=0.5, y=0.75, length=1.0, width=wall_thickness)
    demo.newObstacle("maze_7", x=1.5, y=0.75, length=1.0, width=wall_thickness, psi=np.pi/2)

    # Center row (y = 0.0)
    demo.newObstacle("maze_8", x=-1.0, y=0.0, length=1.0, width=wall_thickness, psi=np.pi/2)
    demo.newObstacle("maze_9", x=0.0, y=0.0, length=1.0, width=wall_thickness)
    demo.newObstacle("maze_10", x=1.0, y=0.0, length=1.0, width=wall_thickness, psi=np.pi/2)

    # Lower-middle row (y = -0.75)
    demo.newObstacle("maze_11", x=-1.5, y=-0.75, length=1.0, width=wall_thickness, psi=np.pi/2)
    demo.newObstacle("maze_12", x=-0.5, y=-0.75, length=1.0, width=wall_thickness)
    demo.newObstacle("maze_13", x=0.5, y=-0.75, length=1.0, width=wall_thickness, psi=np.pi/2)
    demo.newObstacle("maze_14", x=1.5, y=-0.75, length=0.5, width=wall_thickness)

    # Bottom row (y = -1.5)
    demo.newObstacle("maze_15", x=-1.25, y=-1.5, length=1.0, width=wall_thickness, psi=np.pi/2)
    demo.newObstacle("maze_16", x=0.0, y=-1.5, length=1.0, width=wall_thickness)
    demo.newObstacle("maze_17", x=1.25, y=-1.5, length=1.0, width=wall_thickness, psi=np.pi/2)

    # Add goal tasks for the three robots
    demo.newTask("goal1", x=1.5, y=1.5, color=[0, 1, 0])
    demo.newTask("goal2", x=-1.5, y=-1.5, color=[1, 1, 0])
    demo.newTask("goal3", x=1.5, y=-1.5, color=[0, 0, 1])

    demo.logger.info("Large maze setup complete. 4m x 4m maze with 3 robots and 0.1m wall thickness")


