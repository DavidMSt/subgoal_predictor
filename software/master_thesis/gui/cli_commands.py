from __future__ import annotations

from typing import TYPE_CHECKING

from extensions.cli.cli import Command, CommandArgument, CommandSet

if TYPE_CHECKING:
    from master_thesis.gui.thesis_gui import ThesisGUI


class BILBO_Interactive_CommandSet(CommandSet):

    def __init__(self, example: ThesisGUI):
        super().__init__('example_david')
        self.example = example

        add_robot_command = Command(
            function=self.example.newRobot,
            name='add_robot',
            description='Add a new robot to the simulation',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='robot_id', type=str, description='ID of the robot to add')
            ]
        )

        add_obstacle_command = Command(
            function=self.example.newObstacle,
            name='add_obstacle',
            description='Add an obstacle (visual + simulation)',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='obstacle_id', type=str),
                CommandArgument(name='x', type=float, default=0.0),
                CommandArgument(name='y', type=float, default=0.0),
                CommandArgument(name='length', type=float, default=1.0),
                CommandArgument(name='width', type=float, default=0.3),
            ]
        )

        self.addCommand(add_robot_command)
        self.addCommand(add_obstacle_command)

        assign_joystick_cmd = Command(
            function=self.example.assignJoystick,
            name='assign_joystick',
            description='Assign Xbox controller to a robot',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='robot_id', type=str),
                CommandArgument(name='joystick_id', type=int, default=0),
            ]
        )
        unassign_joystick_cmd = Command(
            function=self.example.unassignJoystick,
            name='unassign_joystick',
            description='Remove joystick from a robot',
            allow_positionals=True,
            arguments=[CommandArgument(name='robot_id', type=str)]
        )
        self.addCommand(assign_joystick_cmd)
        self.addCommand(unassign_joystick_cmd)
