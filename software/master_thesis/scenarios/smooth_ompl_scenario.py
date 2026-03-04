from master_thesis.scenarios.base import (
    AgentSpec,
    ObstacleSpec,
    ScenarioConfig,
    ScenarioFactory,
    TaskSpec,
)

class SmoothOMPLTest(ScenarioFactory):
    """Manual joystick-driving test: one driveable agent, one autonomous agent, one wall.

    Layout (2x2 m arena):
      - Horizontal wall at y=0 blocking the centre
      - frodo0 at (0, -1) facing north → assign joystick to this one and drive into the wall
      - frodo1 at (-1.5, 0.8) facing east → pre-assigned to task_right
      - task_right at (1.5, 0.8) on the open side

    Use this to test:
      - Does the wall stop the joystick-driven agent?
      - Does the autonomous agent plan around the wall correctly?
    """

    name = "smooth_ompl_test"

    @classmethod
    def create(cls) -> ScenarioConfig:
        return ScenarioConfig(
            name=cls.name,
            limits=((-2, 2), (-2, 2)),
            obstacles=[
                ObstacleSpec("wall_centre", x=0.0, y=0.0, length=3.0, width=0.2),
            ],
            agents=[
                AgentSpec("frodo0", "FRODOOfflineAgent", start_config=(0.0, -1.0, math.pi / 2)),
                AgentSpec("frodo1", "FRODOOfflineAgent", start_config=(-1.5, 0.8, 0.0)),
            ],
            tasks=[
                TaskSpec("task_right", x=1.5, y=0.8),
            ],
            assignments={
                "frodo0": "task_right",
            },
        )