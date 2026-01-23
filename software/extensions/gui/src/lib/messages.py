import dataclasses
from typing import Any


@dataclasses.dataclass
class AddMessageData:
    type: str  # Type of the object being added (e.g., 'page', 'category', 'object')
    parent: str  # UID of the parent object (category or GUI)
    id: str  # UID of the object being added
    config: dict | Any  # Configuration data for the object being added
    position: int | None = None  # Optional position for the object (e.g., page position in category)


@dataclasses.dataclass
class AddMessage:
    data: AddMessageData
    type: str = 'add'


@dataclasses.dataclass
class RemoveMessageData:
    type: str
    parent: str  # UID of the parent object (category or GUI)
    id: str  # UID of the object being removed


@dataclasses.dataclass
class RemoveMessage:
    data: RemoveMessageData
    type: str = 'remove'


@dataclasses.dataclass
class RequestMessageData:
    type: str
    id: str  # ID of the requested category or object


@dataclasses.dataclass
class RequestMessage:
    request_id: str
    data: RequestMessageData
    type: str = 'request'


@dataclasses.dataclass
class ResponseMessage:
    request_id: str
    data: dict | Any  # Data returned in response to a request
    type: str = 'response'


@dataclasses.dataclass
class HandshakeMessage:
    data: dict
    type: str = 'handshake'
