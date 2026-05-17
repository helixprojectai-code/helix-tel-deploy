import json
import pytest
from tel_deploy.hub import TELMeshHub


class MockWriter:
    def __init__(self):
        self.buffer = b""
        self._closed = False

    def write(self, data: bytes):
        self.buffer += data

    async def drain(self):
        pass

    def close(self):
        self._closed = True

    async def wait_closed(self):
        pass

    def get_extra_info(self, key):
        return ("127.0.0.1", 9999) if key == "peername" else None

    def messages(self):
        """Return list of decoded JSON messages written to this writer."""
        parts = [part for part in self.buffer.split(b"\n") if part.strip()]
        return [json.loads(part) for part in parts]


class MockReader:
    def __init__(self, lines: list):
        self._lines = [
            (item if isinstance(item, bytes) else (json.dumps(item).encode() + b"\n"))
            for item in lines
        ] + [b""]

    async def readline(self):
        if self._lines:
            return self._lines.pop(0)
        return b""


def msg(d: dict) -> dict:
    return d


# --- Registration ---


@pytest.mark.asyncio
async def test_register_node():
    hub = TELMeshHub()
    reader = MockReader([{"action": "register", "node_id": "OUTTIE"}])
    writer = MockWriter()
    await hub.handle_client(reader, writer)
    # Node should be cleaned up on EOF but was registered during the session
    # We verify by testing routing in a live hub below


@pytest.mark.asyncio
async def test_node_deregistered_on_disconnect():
    hub = TELMeshHub()
    reader = MockReader([{"action": "register", "node_id": "SPIDER"}])
    writer = MockWriter()
    await hub.handle_client(reader, writer)
    assert "SPIDER" not in hub.nodes


@pytest.mark.asyncio
async def test_route_message_to_registered_target():
    hub = TELMeshHub()
    target_writer = MockWriter()
    hub.nodes["SPIDER"] = target_writer
    hub.writer_to_node[target_writer] = "SPIDER"

    reader = MockReader(
        [
            {"action": "register", "node_id": "OUTTIE"},
            {
                "action": "send",
                "target": "SPIDER",
                "payload": {"cipher_b64": "abc", "nonce": 1},
            },
        ]
    )
    sender_writer = MockWriter()
    await hub.handle_client(reader, sender_writer)

    msgs = target_writer.messages()
    assert len(msgs) == 1
    assert msgs[0]["action"] == "route"
    assert msgs[0]["sender"] == "OUTTIE"
    assert msgs[0]["payload"] == {"cipher_b64": "abc", "nonce": 1}


@pytest.mark.asyncio
async def test_route_unknown_target_does_not_crash():
    hub = TELMeshHub()
    reader = MockReader(
        [
            {"action": "register", "node_id": "OUTTIE"},
            {
                "action": "send",
                "target": "GHOST",
                "payload": {"cipher_b64": "x", "nonce": 1},
            },
        ]
    )
    writer = MockWriter()
    await hub.handle_client(reader, writer)
    # No exception raised, nothing written to sender


@pytest.mark.asyncio
async def test_broadcast_reaches_all_other_nodes():
    hub = TELMeshHub()
    node_b = MockWriter()
    node_c = MockWriter()
    hub.nodes["B"] = node_b
    hub.nodes["C"] = node_c
    hub.writer_to_node[node_b] = "B"
    hub.writer_to_node[node_c] = "C"

    reader = MockReader(
        [
            {"action": "register", "node_id": "A"},
            {"action": "broadcast", "payload": {"cipher_b64": "bcast", "nonce": 1}},
        ]
    )
    sender_writer = MockWriter()
    await hub.handle_client(reader, sender_writer)

    b_msgs = node_b.messages()
    c_msgs = node_c.messages()
    assert len(b_msgs) == 1
    assert b_msgs[0]["action"] == "route"
    assert b_msgs[0]["sender"] == "A"
    assert len(c_msgs) == 1
    assert c_msgs[0]["sender"] == "A"


@pytest.mark.asyncio
async def test_broadcast_does_not_echo_to_sender():
    hub = TELMeshHub()
    reader = MockReader(
        [
            {"action": "register", "node_id": "A"},
            {"action": "broadcast", "payload": {"cipher_b64": "bcast", "nonce": 1}},
        ]
    )
    sender_writer = MockWriter()
    await hub.handle_client(reader, sender_writer)
    # sender_writer should have received nothing (no route back to self)
    route_msgs = [m for m in sender_writer.messages() if m.get("action") == "route"]
    assert len(route_msgs) == 0


@pytest.mark.asyncio
async def test_list_nodes_returns_registered_nodes():
    hub = TELMeshHub()
    existing_writer = MockWriter()
    hub.nodes["BESS"] = existing_writer
    hub.writer_to_node[existing_writer] = "BESS"

    reader = MockReader(
        [
            {"action": "register", "node_id": "OUTTIE"},
            {"action": "list_nodes"},
        ]
    )
    writer = MockWriter()
    await hub.handle_client(reader, writer)

    msgs = writer.messages()
    node_list_msg = next((m for m in msgs if m.get("action") == "node_list"), None)
    assert node_list_msg is not None
    assert "BESS" in node_list_msg["nodes"]
    assert "OUTTIE" in node_list_msg["nodes"]


@pytest.mark.asyncio
async def test_stale_writer_removed_on_reregistration():
    hub = TELMeshHub()
    old_writer = MockWriter()
    hub.nodes["SPIDER"] = old_writer
    hub.writer_to_node[old_writer] = "SPIDER"

    new_reader = MockReader([{"action": "register", "node_id": "SPIDER"}])
    new_writer = MockWriter()
    await hub.handle_client(new_reader, new_writer)

    # old_writer should have been evicted from writer_to_node
    assert old_writer not in hub.writer_to_node


@pytest.mark.asyncio
async def test_malformed_json_does_not_crash_hub():
    hub = TELMeshHub()
    reader = MockReader([b"not valid json\n", b"also bad {{{{\n"])
    writer = MockWriter()
    await hub.handle_client(reader, writer)
    # No exception, hub still running (handler returned cleanly)


@pytest.mark.asyncio
async def test_disconnect_removes_node():
    hub = TELMeshHub()
    reader = MockReader([{"action": "register", "node_id": "OUTTIE"}])
    writer = MockWriter()
    await hub.handle_client(reader, writer)
    assert "OUTTIE" not in hub.nodes
    assert writer not in hub.writer_to_node
