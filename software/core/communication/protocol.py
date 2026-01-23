import dataclasses
import time as t


@dataclasses.dataclass
class JSON_Message:
    address: str | dict = None
    source: str = None

    type: str = None
    time: float = None
    id: int = 0
    event: str = None
    request_id: int = 0
    request_response: bool = False
    data: dict = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        self.id = id(self)
        self.time = t.time()
