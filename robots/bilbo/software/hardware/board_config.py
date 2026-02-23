import dataclasses
import enum

from dacite import Config

from core.utils.dataclass_utils import from_dict
from core.utils.files import file_exists, deleteFile
from core.utils.json_utils import readJSON, writeJSON
from robot.paths import CONFIG_PATH


class BoardRevision(enum.StrEnum):
    REV3 = 'rev3'
    REV4 = 'rev4'
    REV4_1 = 'rev4.1'


class ComputeModule(enum.StrEnum):
    CM4 = 'cm4'
    CM5 = 'cm5'


class PinType(enum.StrEnum):
    SX1508 = 'sx1508'
    SX1509 = 'sx1509'
    INTERNAL = 'internal'


@dataclasses.dataclass
class Pin:
    type: PinType
    pin: int


@dataclasses.dataclass
class BoardPins:
    status_led: Pin
    new_samples_interrupt: Pin
    uart_reset: Pin
    stm32_reset: Pin
    stm32_boot0: Pin


@dataclasses.dataclass
class BoardSerialCommunication:
    device: str
    baud: int


@dataclasses.dataclass
class BoardCommunication:
    serial: BoardSerialCommunication


@dataclasses.dataclass
class BoardDeviceAddresses:
    gpio_extender: int
    shield_eeprom: int
    io_extension: int


@dataclasses.dataclass
class BoardDefinition:
    pins: BoardPins
    communication: BoardCommunication
    devices: BoardDeviceAddresses


@dataclasses.dataclass
class RobotControlBoardConfig:
    revision: BoardRevision
    definitions: BoardDefinition
    compute_module: ComputeModule


# ----------------------------------------------------------------------------------------------------------------------
REV4_PINS = BoardPins(
    status_led=Pin(PinType.SX1508, 2),
    new_samples_interrupt=Pin(PinType.INTERNAL, 6),
    uart_reset=Pin(PinType.INTERNAL, 16),
    stm32_reset=Pin(PinType.SX1508, 5),
    stm32_boot0=Pin(PinType.SX1508, 3),
)

REV3_PINS = BoardPins(
    status_led=Pin(PinType.SX1508, 3),
    new_samples_interrupt=Pin(PinType.INTERNAL, 16),
    uart_reset=Pin(PinType.INTERNAL, 5),
    stm32_reset=Pin(PinType.SX1508, 5),
    stm32_boot0=Pin(PinType.SX1508, 0),
)

REV4_1_PINS = BoardPins(
    status_led=Pin(PinType.SX1509, 8),
    new_samples_interrupt=Pin(PinType.INTERNAL, 6),
    uart_reset=Pin(PinType.SX1509, 10),
    stm32_reset=Pin(PinType.SX1509, 11),
    stm32_boot0=Pin(PinType.SX1509, 14),

)


# ----------------------------------------------------------------------------------------------------------------------
def generateBoardConfig(board_rev: str, cm_type: str):

    # Check if there is a prefix with "rev"
    if not board_rev.startswith("rev"):
        board_rev = f"rev{board_rev}"

    if board_rev not in ['rev3', 'rev4', 'rev4.1']:
        print("Invalid board revision. Must be one of 'rev3', 'rev4', or 'rev4.1'.")
        return

    if cm_type not in ['cm4', 'cm5']:
        print("Invalid compute module type. Must be one of 'cm4' or 'cm5'.")

    revision = BoardRevision(board_rev)
    cm_type = ComputeModule(cm_type)

    if revision == BoardRevision.REV3:
        pins = REV3_PINS
    elif revision == BoardRevision.REV4:
        pins = REV4_PINS
    elif revision == BoardRevision.REV4_1:
        pins = REV4_1_PINS
    else:
        return

    if cm_type == ComputeModule.CM4:
        communication = BoardCommunication(
            serial=BoardSerialCommunication(device='/dev/ttyAMA5', baud=1000000))
    elif cm_type == ComputeModule.CM5:
        communication = BoardCommunication(
            serial=BoardSerialCommunication(device='/dev/ttyAMA4', baud=1000000))

    if revision == BoardRevision.REV4_1:
        devices = BoardDeviceAddresses(gpio_extender=0x3E, shield_eeprom=0x53, io_extension=0x01)
    elif revision == BoardRevision.REV4:
        devices = BoardDeviceAddresses(gpio_extender=0x20, shield_eeprom=0x53, io_extension=0x01)
    elif revision == BoardRevision.REV3:
        devices = BoardDeviceAddresses(gpio_extender=0x20, shield_eeprom=0x53, io_extension=0x01)
    else:
        return

    board_config = RobotControlBoardConfig(
        revision=revision,
        definitions=BoardDefinition(pins=pins, communication=communication, devices=devices),
        compute_module=cm_type,

    )

    board_config_dict = dataclasses.asdict(board_config)
    writeJSON(f"{CONFIG_PATH}/board.json", board_config_dict)
    print(f"Board config file generated for revision {board_rev} and compute module {cm_type}")


# ======================================================================================================================
def getBoardConfig() -> RobotControlBoardConfig | None:
    file = f"{CONFIG_PATH}/board.json"
    if not file_exists(file):
        return None

    data_dict = readJSON(file)
    config = from_dict(
        data_class=RobotControlBoardConfig,
        data=data_dict,
        config=Config(
            type_hooks={
                BoardRevision: BoardRevision,
                ComputeModule: ComputeModule,
                PinType: PinType,
            }
        )
    )
    return config


if __name__ == '__main__':
    ...
