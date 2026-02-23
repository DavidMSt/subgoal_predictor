import uuid

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def _int_to_base62(num: int) -> str:
    """Convert an integer to a Base62 string."""
    if num == 0:
        return _ALPHABET[0]
    base62 = []
    while num:
        num, rem = divmod(num, 62)
        base62.append(_ALPHABET[rem])
    return "".join(reversed(base62))


def generate_uuid(prefix: str = "", suffix: str = "") -> str:
    """
    Generate a short, alphanumeric unique ID using Base62-encoded UUID4.

    Args:
        prefix (str): Optional string to prepend.
        suffix (str): Optional string to append.

    Returns:
        str: A short unique identifier (only letters and numbers).
    """
    u = uuid.uuid4().int  # 128-bit integer
    short_id = _int_to_base62(u)
    return f"{prefix}{short_id}{suffix}"
