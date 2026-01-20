from datetime import datetime

import time

from _tests.timecode.timecode_listener import TimecodeListener
from core.utils.files import get_absolute_path
from robot.bilbo import BILBO
from core.utils.logging_utils import setLoggerLevel, Logger
from robot.control.bilbo_control_definitions import BILBO_Control_Mode
from robot.experiment.bilbo_experiment import ExperimentDefinition, BeepAction, SpeakAction, SetModeAction, \
    SetTICAction, WaitTickAction, RunTrajectoryAction, ExperimentMetaData, ExperimentData, ExperimentActionDefinition
from robot.experiment.helpers import generate_random_input_trajectory
from robot.logging.bilbo_sample import BILBO_Sample


def main():
    bilbo = BILBO(reset_stm32=False)
    bilbo.init()
    bilbo.start()

    # time.sleep(3)
    # bilbo.control.set_mode(BILBO_Control_Mode.BALANCING)
    # time.sleep(5)
    # bilbo.control.enable_tic_control(True)
    # time.sleep(15)
    # bilbo.control.set_mode(BILBO_Control_Mode.OFF)

    while True:
        time.sleep(1)



if __name__ == '__main__':
    main()
