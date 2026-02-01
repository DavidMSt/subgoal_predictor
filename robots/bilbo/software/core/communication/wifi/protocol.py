import dataclasses
import logging
import time as t

import numpy
import orjson



def default_numpy_json(obj):
    if isinstance(obj, numpy.generic):
        return obj.item()  # Convert to native Python type
    raise TypeError


# ======================================================================================================================
@dataclasses.dataclass
class JSON_Message:
    address: str = ''
    source: str = ''

    type: str = ''
    time: float = 0
    id: int = 0
    event: str | None = ''
    request_id: int = 0
    request_response: bool = False
    data: dict = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        self.id = id(self)
        self.time = t.time()

