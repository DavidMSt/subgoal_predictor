import warnings
import orjson
import numpy as np
from core.utils.files import file_exists


def _default(obj):
    """
    Custom serializer for orjson.
    Handles numpy arrays and scalars.
    """
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.generic,)):  # e.g. np.int32, np.float64
        return obj.item()
    raise TypeError


def jsonEncode(obj):
    opts = orjson.OPT_NON_STR_KEYS
    return orjson.dumps(obj, option=opts, default=_default, )


def readJSON(file) -> dict | None:
    if not file_exists(file):
        warnings.warn(f"File {file} does not exist", UserWarning)
        return None
    with open(file, "rb") as f:  # must read bytes
        return orjson.loads(f.read())


def writeJSON(file, data, pretty: bool = True):
    opts = (orjson.OPT_INDENT_2 if pretty else 0) | orjson.OPT_NON_STR_KEYS
    with open(file, "wb") as f:  # must write bytes
        f.write(orjson.dumps(data, option=opts, default=_default))
