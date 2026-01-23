import base64
import os

def load_image_base64(path: str) -> str:
    """
    Given a filesystem path to e.g. a PNG, return the
    base64‑encoded string (no data:… prefix).
    """
    full = os.path.abspath(path)
    with open(full, "rb") as f:
        data = f.read()
    # b64encode returns bytes, so decode to str
    return base64.b64encode(data).decode("ascii")