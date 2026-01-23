import dataclasses
from abc import ABC, abstractmethod


@dataclasses.dataclass
class DataPacket:
    pass


class Message:
    _protocol: 'Protocol' = None

    def encode(self, *args, **kwargs):
        return self._protocol.encode(self, *args, **kwargs)


class Protocol(ABC):
    Message: type
    base: 'Protocol'
    identifier: int

    def __init__(self):
        pass

    @abstractmethod
    def decode(self, data):
        pass

    @abstractmethod
    def encode(self, msg: Message, *args, **kwargs):
        pass

    @abstractmethod
    def check(self, data):
        pass
