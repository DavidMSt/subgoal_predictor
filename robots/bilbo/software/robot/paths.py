import os

ROBOT_PATH = os.path.expanduser('~/robot/')
CONFIG_PATH = os.path.expanduser('~/robot/config/')
EXPERIMENTS_PATH = os.path.expanduser('~/robot/experiments/')
LOGS_PATH = os.path.expanduser('~/robot/logs/')
CONTROL_PATH = os.path.expanduser('~/robot/control/')
CALIBRATION_PATH = os.path.expanduser('~/robot/calibration/')
SOFTWARE_PATH = os.path.expanduser('~/robot/software/')


def init_paths(robot_path: str):
    """Override all paths with a custom robot root directory.

    Must be called BEFORE importing any module that uses these paths
    (i.e. before ``from robot.bilbo import BILBO``).
    """
    global ROBOT_PATH, CONFIG_PATH, EXPERIMENTS_PATH, LOGS_PATH
    global CONTROL_PATH, CALIBRATION_PATH, SOFTWARE_PATH

    robot_path = os.path.expanduser(robot_path)
    if not robot_path.endswith('/'):
        robot_path += '/'

    ROBOT_PATH = robot_path
    CONFIG_PATH = robot_path + 'config/'
    EXPERIMENTS_PATH = robot_path + 'experiments/'
    LOGS_PATH = robot_path + 'logs/'
    CONTROL_PATH = robot_path + 'control/'
    CALIBRATION_PATH = robot_path + 'calibration/'
    SOFTWARE_PATH = robot_path + 'software/'

