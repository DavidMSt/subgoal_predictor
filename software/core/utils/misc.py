import time


def clipValue(value, max_value, min_value=0):
    if value > max_value:
        return max_value
    elif value < min_value:
        return min_value
    else:
        return value


# ======================================================================================================================
def getFromDict(dict, key, default=None):
    if hasattr(dict, key):
        return dict[key]
    else:
        return default


# ======================================================================================================================
def waitForKeyboardInterrupt():
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        ...
