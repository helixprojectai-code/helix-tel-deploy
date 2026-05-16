import json
from tel_deploy.protocol import build_message, parse_message, MessageType


def test_build_message_basic():
    result = build_message(MessageType.TASK, "do something")
    parsed = json.loads(result)
    assert parsed["type"] == "task"
    assert parsed["body"] == "do something"


def test_build_message_no_metadata_by_default():
    result = build_message(MessageType.HEARTBEAT, "ping")
    parsed = json.loads(result)
    assert "meta" not in parsed


def test_build_message_with_metadata():
    result = build_message(MessageType.STATUS, "ok", metadata={"node": "OUTTIE"})
    parsed = json.loads(result)
    assert parsed["meta"] == {"node": "OUTTIE"}


def test_build_message_all_types():
    for mt in MessageType:
        result = build_message(mt, "body")
        parsed = json.loads(result)
        assert parsed["type"] == mt.value


def test_parse_valid_message():
    raw = json.dumps({"type": "task", "body": "run recon"})
    msg = parse_message(raw)
    assert msg["type"] == "task"
    assert msg["body"] == "run recon"


def test_parse_message_with_meta():
    raw = json.dumps({"type": "ack", "body": "received", "meta": {"seq": 1}})
    msg = parse_message(raw)
    assert msg["meta"]["seq"] == 1


def test_parse_invalid_json_returns_error():
    msg = parse_message("not json {{{")
    assert msg["type"] == "error"
    assert "not json" in msg["body"]


def test_parse_missing_type_returns_error():
    raw = json.dumps({"body": "no type field"})
    msg = parse_message(raw)
    assert msg["type"] == "error"


def test_parse_missing_body_returns_error():
    raw = json.dumps({"type": "task"})
    msg = parse_message(raw)
    assert msg["type"] == "error"


def test_build_then_parse_round_trip():
    original = build_message(MessageType.BROADCAST, "all nodes attention")
    parsed = parse_message(original)
    assert parsed["type"] == "broadcast"
    assert parsed["body"] == "all nodes attention"
