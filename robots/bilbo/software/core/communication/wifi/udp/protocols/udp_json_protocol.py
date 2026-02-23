import dataclasses
import logging
import time
import orjson

from core.communication.protocol import Protocol, Message
from .udp_base_protocol import UDP_Base_Protocol


# ======================================================================================================================
@dataclasses.dataclass
class UDP_JSON_Message(Message):
    data: dict = dataclasses.field(default_factory=dict)
    address: (str, dict) = None
    source: str = None
    type: str = None
    meta: dict = dataclasses.field(default_factory=dict)
    event: str = None

    def __init__(self):
        self.meta = {
            'time': time.time(),
            'id': id(self),
            'source': '',
            'address': '',
            'port': '',
        }


# ======================================================================================================================
class UDP_JSON_Protocol(Protocol):
    base = UDP_Base_Protocol
    Message = UDP_JSON_Message
    identifier = 0x02
    allowed_types = [None, 'event', 'broadcast']
    meta_fields = ['time', 'id', 'source', 'address', 'port']

    # ------------------------------------------------------------------------------------------------------------------
    @classmethod
    def decode(cls, data: bytes):
        assert (isinstance(data, bytes))
        msg = cls.Message()
        msg_content = orjson.loads(data)

        if 'data' in msg_content:
            msg.data = msg_content['data']
        else:
            msg.data = {}
        if 'address' in msg_content:
            msg.address = msg_content['address']
        if 'source' in msg_content:
            msg.source = msg_content['source']
        if 'type' in msg_content:
            msg.type = msg_content['type']
        if 'event' in msg_content:
            msg.event = msg_content['event']
        if 'meta' in msg_content:
            msg.meta = msg_content['meta']
        return msg

    # ------------------------------------------------------------------------------------------------------------------
    @classmethod
    def encode(cls, msg: UDP_JSON_Message, source_address=None, target_address=None, port=None, *args, **kwargs):
        # Check if the command is allowed
        if msg.type not in cls.allowed_types:
            logging.error(f"Command not allowed!")
            return

        msg.meta['source'] = source_address
        msg.meta['address'] = target_address
        msg.meta['port'] = port

        # Check if the metadata is present
        for f in cls.meta_fields:
            if f not in msg.meta:
                logging.error(f'Meta data {f} missing. Message not encoded.')
                return

        # Check if it correctly set up for a command
        data = orjson.dumps(msg)

        return data

    @classmethod
    def check(cls, data):
        return 1


UDP_JSON_Message._protocol = UDP_JSON_Protocol
