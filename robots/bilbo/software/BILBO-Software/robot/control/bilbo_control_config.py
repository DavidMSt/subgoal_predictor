import math

from core.utils.files import file_exists

from robot.control.bilbo_control_data import BILBO_ControlConfig, BILBO_Control_Mode, General_Control_Config, \
    ExternalInputsConfig, TWIPR_Balancing_Control_Config, TIC_Config, VIC_Config
from core.utils.json_utils import writeJSON, readJSON
from core.utils.dataclass_utils import asdict_optimized, from_dict
from robot.paths import CONTROL_PATH

config_bilbo_normal = BILBO_ControlConfig(
    name='default_normal',
    description='Default configuration for normal BILBO',
    mode=BILBO_Control_Mode.OFF,
    general=General_Control_Config(
        max_wheel_speed=100,
        max_wheel_torque=0.5,
    ),
    external_inputs=ExternalInputsConfig(
        balancing_input_gain={
            'forward': 0.3,
            'turn': 0.12
        },
        speed_input_gain={
            'forward': 0,
            'turn': 0
        }
    ),
    balancing_control=TWIPR_Balancing_Control_Config(
        # K=[0.3, 0.42, 0.04, 0.025,
        #    0.3, 0.42, 0.04, -0.025],

        # Standard and aggressive
        # K=[0.25, 0.35, 0.04, 0.025,
        #    0.25, 0.35, 0.04, -0.025],

        K=[0.25, 0.32, 0.03, 0.025,
           0.25, 0.32, 0.03, -0.025],
        # tic=TIC_Config(
        #     enabled=False,
        #     ki=0.2,
        #     max_error=0.3,
        #     theta_limit=math.radians(10)
        # ),
        tic=TIC_Config(
            enabled=False,
            ki=0.4,
            max_error=0.5,
            theta_limit=math.radians(10)
        ),
        vic=VIC_Config(
            enabled=True,
            ki=0.2,
            max_error=0.3,
            v_limit=0.1
        )
    ),
)

config_bilbo_hhi = BILBO_ControlConfig(
    name='default_hhi',
    description='Default configuration for normal BILBO',
    mode=BILBO_Control_Mode.OFF,
    general=General_Control_Config(
        max_wheel_speed=100,
        max_wheel_torque=0.3,
    ),
    external_inputs=ExternalInputsConfig(
        balancing_input_gain={
            'forward': 0.2,
            'turn': 0.1
        },
        speed_input_gain={
            'forward': 0,
            'turn': 0
        }
    ),
    balancing_control=TWIPR_Balancing_Control_Config(
        # K=[0.3, 0.42, 0.04, 0.025,
        #    0.3, 0.42, 0.04, -0.025],
        K=[0.15, 0.17, 0.017, 0.015,
           0.15, 0.17, 0.017, -0.015],
        tic=TIC_Config(
            enabled=False,
            ki=0.2,
            max_error=0.3,
            theta_limit=math.radians(10)
        ),
        vic=VIC_Config(
            enabled=False,
            ki=0.1,
            max_error=0.3,
            v_limit=0.05
        )
    ),
)

config_bilbo_big = BILBO_ControlConfig(
    name='default_big',
    description='Default configuration for big BILBO',
    mode=BILBO_Control_Mode.OFF,
    general=General_Control_Config(
        max_wheel_speed=100,
        max_wheel_torque=0.5,
    ),
    external_inputs=ExternalInputsConfig(
        balancing_input_gain={
            'forward': 0.3,
            'turn': 0.12
        },
        speed_input_gain={
            'forward': 0,
            'turn': 0
        }
    ),
    balancing_control=TWIPR_Balancing_Control_Config(
        K=[0.2, 0.28, 0.035, 0.02,
           0.2, 0.28, 0.035, -0.02],
        tic=TIC_Config(
            enabled=False,
            ki=0.4,
            max_error=0.6,
            theta_limit=math.radians(10)
        ),
        vic=VIC_Config(
            enabled=True,
            ki=0.2,
            max_error=0.5,
            v_limit=0.1
        )
    ),
)

config_bilbo_small = BILBO_ControlConfig(
    name='default_small',
    description='Default configuration for small BILBO',
    mode=BILBO_Control_Mode.OFF,
    general=General_Control_Config(
        max_wheel_speed=100,
        max_wheel_torque=0.5,
    ),
    external_inputs=ExternalInputsConfig(
        balancing_input_gain={
            'forward': 0.35,
            'turn': 0.2
        },
        speed_input_gain={
            'forward': 0,
            'turn': 0
        }
    ),
    balancing_control=TWIPR_Balancing_Control_Config(
        K=[0.16, 0.3, 0.030, 0.02,
           0.16, 0.3, 0.030, -0.02],
        tic=TIC_Config(
            enabled=False,
            ki=0.25,
            max_error=0.5,
            theta_limit=math.radians(10)
        ),
        vic=VIC_Config(
            enabled=True,
            ki=0.2,
            max_error=0.5,
            v_limit=0.1
        )
    ),
)


def load_config(name: str) -> BILBO_ControlConfig:
    # Check if the file exists
    if not file_exists(f"{CONTROL_PATH}{name}.json"):
        raise FileNotFoundError(f"Config file '{name}.json' not found in '{CONTROL_PATH}'")

    control_config_dict = readJSON(f"{CONTROL_PATH}{name}.json")

    return from_dict(BILBO_ControlConfig, control_config_dict)


def generate_default_config(model: str):
    if model in ['normal', 'bilbo1', 'bilbo2']:
        config = config_bilbo_normal
    elif model == 'big':
        config = config_bilbo_big
    elif model == 'mini':
        config = config_bilbo_small
    elif model == 'hhi':
        config = config_bilbo_hhi
    else:
        raise ValueError("Model must be either 'normal', 'big', 'mini' or 'hhi'")


    config_dict = asdict_optimized(config)
    file = f"{CONTROL_PATH}default.json"
    writeJSON(file, config_dict)
    print(f"Config file 'default.json' generated in '{CONTROL_PATH}'")


if __name__ == '__main__':
    generate_default_config('normal')