"""Built-in TCP/WebSocket proxy and WOL relay for cross-VLAN TV control."""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any

from aiohttp import web
from wakeonlan import send_magic_packet

_LOGGER = logging.getLogger(__name__)


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
        pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def _handle_client(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    tv_host: str,
    tv_port: int,
) -> None:
    peer = client_writer.get_extra_info("peername")
    try:
        remote_reader, remote_writer = await asyncio.open_connection(tv_host, tv_port)
    except OSError as exc:
        _LOGGER.warning("Relay upstream connect failed %s:%s — %s", tv_host, tv_port, exc)
        client_writer.close()
        return
    _LOGGER.debug("Relay connection %s -> %s:%s", peer, tv_host, tv_port)
    await asyncio.gather(
        _pipe(client_reader, remote_writer),
        _pipe(remote_reader, client_writer),
    )


async def _wol_handler(request: web.Request) -> web.Response:
    data: dict[str, Any] = await request.json()
    mac = data.get("mac")
    if not mac:
        return web.json_response({"error": "mac required"}, status=400)
    broadcast = data.get("broadcast")
    if broadcast:
        send_magic_packet(mac, ip_address=broadcast)
    else:
        send_magic_packet(mac)
    _LOGGER.info("Relay sent WOL to %s", mac)
    return web.json_response({"status": "ok"})


async def run_relay(
    tv_host: str,
    listen_host: str,
    listen_port: int,
    tv_port: int,
    wol_port: int,
    listen_port_alt: int | None = None,
) -> None:
    """Run TCP proxy and optional WOL HTTP server."""
    servers: list[asyncio.AbstractServer] = []

    async def start_proxy(port: int, upstream_port: int) -> None:
        server = await asyncio.start_server(
            lambda r, w: _handle_client(r, w, tv_host, upstream_port),
            host=listen_host,
            port=port,
        )
        servers.append(server)
        _LOGGER.info("Relay listening on %s:%s -> %s:%s", listen_host, port, tv_host, upstream_port)

    await start_proxy(listen_port, tv_port)
    if listen_port_alt is not None and listen_port_alt != listen_port:
        alt_upstream = 8001 if tv_port == 8002 else 8001
        await start_proxy(listen_port_alt, alt_upstream)

    wol_app = web.Application()
    wol_app.router.add_post("/wol", _wol_handler)
    runner = web.AppRunner(wol_app)
    await runner.setup()
    site = web.TCPSite(runner, listen_host, wol_port)
    await site.start()
    _LOGGER.info("WOL endpoint http://%s:%s/wol", listen_host, wol_port)

    try:
        await asyncio.Event().wait()
    finally:
        for server in servers:
            server.close()
            await server.wait_closed()
        await runner.cleanup()


def main() -> None:
    """CLI entry point for smartthings-mqtt-relay."""
    parser = argparse.ArgumentParser(description="Samsung TV VLAN relay proxy")
    parser.add_argument("--tv-host", required=True, help="TV IP on local VLAN")
    parser.add_argument("--tv-port", type=int, default=8002, help="TV upstream port")
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=8002)
    parser.add_argument("--listen-port-alt", type=int, default=8001)
    parser.add_argument("--wol-port", type=int, default=8080)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    asyncio.run(
        run_relay(
            tv_host=args.tv_host,
            listen_host=args.listen_host,
            listen_port=args.listen_port,
            tv_port=args.tv_port,
            wol_port=args.wol_port,
            listen_port_alt=args.listen_port_alt,
        )
    )


if __name__ == "__main__":
    main()
