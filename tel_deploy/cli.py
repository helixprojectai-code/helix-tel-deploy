import asyncio
import json
import logging
import os
import click
from .config import load_config
from .client import TELClient
from .protocol import build_message, MessageType
from .hub import run_hub

LOG_FORMAT = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"


def setup_logging(cfg):
    level = getattr(logging, cfg["logging"]["level"].upper(), logging.INFO)
    handlers = [logging.StreamHandler()]
    if cfg["logging"].get("file"):
        handlers.append(logging.FileHandler(cfg["logging"]["file"]))
    logging.basicConfig(level=level, format=LOG_FORMAT, handlers=handlers)


@click.group()
@click.option("--config", "-c", default=None, help="Path to tel.yaml config file")
@click.pass_context
def cli(ctx, config):
    """TEL — Trefoil Encrypted Link Mesh CLI"""
    ctx.ensure_object(dict)
    ctx.obj["cfg"] = load_config(config)
    setup_logging(ctx.obj["cfg"])


@cli.command()
@click.pass_context
def hub(ctx):
    """Start the TEL Mesh Hub (Bess)"""
    cfg = ctx.obj["cfg"]
    run_hub(cfg["hub"]["host"], cfg["hub"]["port"])


@cli.command()
@click.pass_context
def listen(ctx):
    """Connect to hub and listen for inbound messages"""
    cfg = ctx.obj["cfg"]

    async def _listen():
        client = TELClient(
            cfg["hub"]["host"],
            cfg["hub"]["port"],
            cfg["node"]["id"],
            cfg["node"]["seed"],
            cfg.get("reconnect"),
        )
        await client.connect()
        await client.listen()

    asyncio.run(_listen())


@cli.command()
@click.argument("target")
@click.argument("message")
@click.option(
    "--type",
    "-t",
    "msg_type",
    default="task",
    help="Message type: task|ack|heartbeat|status|broadcast",
)
@click.pass_context
def send(ctx, target, message, msg_type):
    """Encrypt and send a message to TARGET node"""
    cfg = ctx.obj["cfg"]

    async def _send():
        client = TELClient(
            cfg["hub"]["host"],
            cfg["hub"]["port"],
            cfg["node"]["id"],
            cfg["node"]["seed"],
            cfg.get("reconnect"),
        )
        await client.connect()
        payload = build_message(MessageType(msg_type), message)
        await client.send(target, payload)
        await client.close()

    asyncio.run(_send())


@cli.command()
@click.pass_context
def status(ctx):
    """Show connection status and counter state"""
    cfg = ctx.obj["cfg"]

    async def _status():
        client = TELClient(
            cfg["hub"]["host"],
            cfg["hub"]["port"],
            cfg["node"]["id"],
            cfg["node"]["seed"],
            cfg.get("reconnect"),
        )
        await client.connect()
        s = await client.status()
        click.echo(json.dumps(s, indent=2))
        await client.close()

    asyncio.run(_status())


@cli.command()
@click.option("--max-passes", "-m", default=20, help="Max convergence passes")
@click.option("--endpoint", "-e", default=None, help="Model API endpoint URL")
@click.option("--api-key", "-k", default=None, help="API key or Bearer token")
@click.option("--model", default=None, help="Model/deployment name")
@click.option("--azure", is_flag=True, default=False, help="Use Azure OpenAI format")
@click.pass_context
def converge(ctx, max_passes, endpoint, api_key, model, azure):
    """Run convergence detector to derive seed from constitutional shape"""
    from .test_runner import run_convergence_pass

    cfg = ctx.obj["cfg"]
    ep = endpoint or os.environ.get("TEL_CONVERGE_ENDPOINT")
    key = api_key or os.environ.get("TEL_CONVERGE_API_KEY")

    if not ep or not key:
        click.echo(
            "Error: --endpoint and --api-key required (or set TEL_CONVERGE_ENDPOINT / TEL_CONVERGE_API_KEY)"
        )
        return

    async def _converge():
        client = TELClient(
            cfg["hub"]["host"],
            cfg["hub"]["port"],
            cfg["node"]["id"],
            cfg["node"].get("seed"),
            cfg.get("reconnect"),
        )

        async def test_fn():
            click.echo("Running convergence pass (27 active tests, 23C + 4B, from pool of 33)...")
            return await run_convergence_pass(ep, key, model=model, azure=azure)

        success = await client.converge(test_fn, max_passes=max_passes)
        state = client._convergence.get_state()
        click.echo(json.dumps(state, indent=2))

        if success:
            split = client._split.report()
            click.echo(json.dumps(split, indent=2))
            click.echo(f"\nMESH SEED (C): {client._split.get_mesh_seed()[:32]}...")
            click.echo(f"FINGERPRINT (B): {client._split.get_fingerprint()[:32]}...")
            click.echo(f"SUBSTRATE: {client._split.substrate}")
            click.echo("\nConvergence PROVEN. Shape is the key.")
        else:
            click.echo(f"\nFailed to converge within {max_passes} passes.")

    asyncio.run(_converge())


@cli.command()
@click.pass_context
def nodes(ctx):
    """Query hub for active mesh participants"""
    cfg = ctx.obj["cfg"]

    async def _nodes():
        reader, writer = await asyncio.open_connection(
            cfg["hub"]["host"], cfg["hub"]["port"]
        )

        reg = json.dumps({"action": "register", "node_id": cfg["node"]["id"]}) + "\n"
        writer.write(reg.encode())
        await writer.drain()

        req = json.dumps({"action": "list_nodes"}) + "\n"
        writer.write(req.encode())
        await writer.drain()

        data = await reader.readline()
        if data:
            msg = json.loads(data.decode().strip())
            if msg.get("action") == "node_list":
                click.echo("Active nodes:")
                for n in msg["nodes"]:
                    click.echo(f"  \u2022 {n}")
            else:
                click.echo(f"Unexpected response: {msg}")

        writer.close()
        await writer.wait_closed()

    asyncio.run(_nodes())


@cli.command()
@click.option("--max-passes", "-m", default=20, help="Max convergence passes")
@click.option("--endpoint", "-e", default=None, help="Model API endpoint URL")
@click.option("--api-key", "-k", default=None, help="API key or Bearer token")
@click.option("--model", default=None, help="Model/deployment name")
@click.option("--azure", is_flag=True, default=False, help="Use Azure OpenAI format")
@click.option("--node-id", default=None, help="Override node ID from config")
@click.option("--topology", default="universal", help="Constitutional topology")
@click.option("--heartbeat", default=300, help="Ping interval in seconds (default 300)")
@click.pass_context
def node(ctx, max_passes, endpoint, api_key, model, azure, node_id, topology, heartbeat):
    """TEL v2: converge, ping registry, run heartbeat loop."""
    from .test_runner import run_convergence_pass
    from .ping import PingClient

    cfg = ctx.obj["cfg"]
    ep = endpoint or os.environ.get("TEL_CONVERGE_ENDPOINT")
    key = api_key or os.environ.get("TEL_CONVERGE_API_KEY")
    nid = node_id or cfg["node"]["id"]

    if not ep or not key:
        click.echo("Error: --endpoint and --api-key required (or TEL_CONVERGE_ENDPOINT / TEL_CONVERGE_API_KEY)")
        return

    async def _node():
        # --- Phase 1: Convergence ---
        click.echo(f"\n[TEL v2] Node: {nid}  Topology: {topology}")
        click.echo("[TEL v2] Running constitutional battery...")

        client = TELClient(
            cfg["hub"]["host"],
            cfg["hub"]["port"],
            nid,
            cfg["node"].get("seed"),
            cfg.get("reconnect"),
        )

        async def test_fn():
            return await run_convergence_pass(ep, key, model=model, azure=azure)

        converged = await client.converge(test_fn, max_passes=max_passes)

        if not converged:
            click.echo(f"[TEL v2] Failed to converge in {max_passes} passes. Aborting.")
            return

        c_seed = client._split.get_mesh_seed()
        click.echo(f"[TEL v2] Converged. C-seed: {c_seed[:16]}...  Substrate: {client._split.substrate}")

        # --- Phase 2: Ping registry ---
        ping_client = PingClient(node_id=nid, topology=topology)
        click.echo(f"[TEL v2] Pinging registry...")
        response = await ping_client.ping(c_seed=c_seed)
        click.echo(f"[TEL v2] Registry ok. {len(response.peers)} peer(s) known.")

        compatible = response.compatible_peers(topology, ping_client.grammar)
        if compatible:
            click.echo(f"[TEL v2] Compatible peers: {[p.node_id for p in compatible]}")
        else:
            click.echo("[TEL v2] No compatible peers online yet. Heartbeat will watch.")

        # --- Phase 3: Heartbeat ---
        click.echo(f"[TEL v2] Heartbeat every {heartbeat}s. Ctrl+C to stop.\n")

        async def on_peer_change(peers):
            click.echo(f"[TEL v2] Peer set changed: {[p.node_id for p in peers]}")

        await ping_client.start_heartbeat(
            c_seed=c_seed,
            interval=heartbeat,
            on_peer_change=on_peer_change,
        )

    asyncio.run(_node())


if __name__ == "__main__":
    cli()
