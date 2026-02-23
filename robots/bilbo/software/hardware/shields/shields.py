from hardware.shields.bilbo_shield_rev2 import BILBO_Shield_Rev2
from hardware.shields.definitions import *

SHIELDS = {
    BILBO_SHIELD_REV_2_ID: {
        'id': 'bilbo_shield_rev_2',
        'name': 'BILBO Shield Rev 2',
        'config_file': BILBO_SHIELD_REV2_CONFIG_FILE,
        'class': BILBO_Shield_Rev2
    }
}
