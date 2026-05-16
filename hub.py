import asyncio
import json
import logging

log = logging.getLogger("tel.hub")


class TELMeshHub:
    """
    Trefoil Encrypted Link Mesh Hub.
    Blind router — no decryption, no inspection. Readline JSON protocol.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 9999):
        self.host = host
        self.port = port
        self.nodes = {}
        self.writer_to_node = {}

    async def handle_client(self, reader, writer):
        addr = writer.get_extra_info("peername")
        log.info(f"Connection from: {addr}")
        node_id = None

        try:
            while True:
                data = await reader.readline()
                if not data:
                    break

                try:
                    msg = json.loads(data.decode().strip())
                except json.JSONDecodeError:
                    log.error(f"Malformed JSON from {addr}")
                    continue

                action = msg.get("action")

                if action == "register":
                    new_id = msg.get("node_id")
                    # Remove stale entry if this node_id was previously registered on a different writer
                    if new_id in self.nodes and self.nodes[new_id] is not writer:
                        old_writer = self.nodes[new_id]
                        if old_writer in self.writer_to_node:
                            del self.writer_to_node[old_writer]
                    node_id = new_id
                    self.nodes[node_id] = writer
                    self.writer_to_node[writer] = node_id
                    log.info(f"Registered: {node_id} ({addr})")

                elif action == "send":
                    target = msg.get("target")
                    sender = self.writer_to_node.get(writer, "UNKNOWN")
                    route_msg = (
                        json.dumps(
                            {
                                "action": "route",
                                "sender": sender,
                                "payload": msg.get("payload"),
                            }
                        )
                        + "\n"
                    )

                    if target in self.nodes:
                        self.nodes[target].write(route_msg.encode())
                        await self.nodes[target].drain()
                        log.info(f"Routed: {sender} -> {target} ({len(route_msg)}B)")
                    else:
                        log.warning(f"Target '{target}' not registered. Dropping.")

                elif action == "broadcast":
                    sender = self.writer_to_node.get(writer, "UNKNOWN")
                    route_msg = (
                        json.dumps(
                            {
                                "action": "route",
                                "sender": sender,
                                "payload": msg.get("payload"),
                            }
                        )
                        + "\n"
                    )
                    for nid, nwriter in list(self.nodes.items()):
                        if nwriter is not writer:
                            nwriter.write(route_msg.encode())
                            await nwriter.drain()
                    log.info(f"Broadcast: {sender} -> {len(self.nodes) - 1} nodes")

                elif action == "list_nodes":
                    response = (
                        json.dumps(
                            {
                                "action": "node_list",
                                "nodes": list(self.nodes.keys()),
                            }
                        )
                        + "\n"
                    )
                    writer.write(response.encode())
                    await writer.drain()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"Error handling {addr}: {e}")
        finally:
            if node_id and node_id in self.nodes:
                del self.nodes[node_id]
            if writer in self.writer_to_node:
                del self.writer_to_node[writer]
            log.info(f"Disconnected: {node_id or addr}")
            writer.close()
            await writer.wait_closed()

    async def start(self):
        server = await asyncio.start_server(
            self.handle_client, self.host, self.port, limit=4 * 1024 * 1024
        )
        addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
        log.info(f"TEL Mesh Hub active on {addrs}")
        log.info("Constitutional Posture: Blind Routing. No key extraction.")

        async with server:
            await server.serve_forever()


def run_hub(host: str = "0.0.0.0", port: int = 9999):
    hub = TELMeshHub(host, port)
    try:
        asyncio.run(hub.start())
    except KeyboardInterrupt:
        log.info("Hub shutting down.")
