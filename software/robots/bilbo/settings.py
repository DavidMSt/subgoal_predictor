import os

from core.utils.files import get_absolute_path
from core.utils.yaml_utils import load_yaml

SETTINGS_FILE = get_absolute_path('./settings.yaml')
_SETTINGS_DIR = os.path.dirname(SETTINGS_FILE)


def get_settings() -> dict:
    """Load host-side BILBO settings from settings.yaml.

    Paths under the ``paths`` key are resolved relative to the settings file's
    directory so that the YAML can use ``./`` style references.
    """
    data = load_yaml(SETTINGS_FILE)

    # Resolve all paths relative to the settings file location
    paths = data.get('paths')
    if isinstance(paths, dict):
        for key, value in paths.items():
            if isinstance(value, str):
                paths[key] = os.path.normpath(os.path.join(_SETTINGS_DIR, value))

    return data