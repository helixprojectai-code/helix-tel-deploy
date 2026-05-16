import json
from enum import Enum


class MessageType(str, Enum):
    TASK = "task"
    ACK = "ack"
    HEARTBEAT = "heartbeat"
    STATUS = "status"
    BROADCAST = "broadcast"
    ERROR = "error"


def build_message(msg_type: MessageType, body: str, metadata: dict = None) -> str:
    msg = {
        "type": msg_type.value,
        "body": body,
    }
    if metadata:
        msg["meta"] = metadata
    return json.dumps(msg)


def parse_message(raw: str) -> dict:
    try:
        msg = json.loads(raw)
        if "type" not in msg or "body" not in msg:
            return {"type": "error", "body": raw}
        return msg
    except json.JSONDecodeError:
        return {"type": "error", "body": raw}
