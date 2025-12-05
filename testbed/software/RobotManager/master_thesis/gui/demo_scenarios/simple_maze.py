import numpy as np

def setup_simple_maze(demo):
    """
    Setup a simple maze scenario.
    Can be called from thesis_demo without circular imports.
    
    Args:
        demo: ThesisDemo instance
    """
    wall_width = 0.2

    # Add robot at start position
    r = demo.addRobot("frodo1")
    r.sim_agent.state.x = -2.0
    r.sim_agent.state.y = -2.0
    r.sim_agent.state.psi = 0.0
    
    # Create simple maze walls
    # Outer walls (forming a 5x5 box)
    demo.addObstacle("wall_top", x=0.0, y=2.5, length=5.0, width=0.2)
    demo.addObstacle("wall_bottom", x=0.0, y=-2.5, length=5.0, width=0.2)
    demo.addObstacle("wall_left", x=-2.5, y=0.0, length=5.0, width=0.2)
    demo.addObstacle("wall_right", x=2.5, y=0.0, length=5.0, width=0.2)
    
    # Internal obstacles to create maze paths
    demo.addObstacle("obs1", x=-1.0, y=0.0, length=2.0, width=0.2)
    demo.addObstacle("obs2", x=1.0, y=0.5, length=2.0, width=0.2)

    # Add goal task
    demo.addTask("goal1", x=2.0, y=2.0, color=[0, 1, 0])  # Green goal at (2, 2)

    demo.logger.info("Simple maze setup complete. Robot at (-2, -2), goal at (2, 2)")
