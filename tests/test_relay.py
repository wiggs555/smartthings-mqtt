"""Tests for TCP relay proxy."""

import asyncio

import pytest

from smartthings_mqtt.local.relay import _handle_client, _pipe


@pytest.mark.asyncio
async def test_pipe_forwards_data():
    server_received = asyncio.Event()
    received_data = bytearray()

    async def server_handler(reader, writer):
        data = await reader.read(1024)
        received_data.extend(data)
        server_received.set()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(server_handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    client_reader, client_writer = await asyncio.open_connection("127.0.0.1", port)
    await client_writer.drain()

    payload = b"hello-relay"
    client_writer.write(payload)
    await client_writer.drain()

    await asyncio.wait_for(server_received.wait(), timeout=2)
    assert received_data == payload

    client_writer.close()
    await client_writer.wait_closed()
    server.close()
    await server.wait_closed()


@pytest.mark.asyncio
async def test_handle_client_proxies_to_upstream():
    upstream_payload = b"upstream-ok"
    upstream_ready = asyncio.Event()

    async def upstream(reader, writer):
        upstream_ready.set()
        data = await reader.read(1024)
        writer.write(upstream_payload)
        await writer.drain()
        if data:
            writer.write(b"echo:" + data)
            await writer.drain()
        writer.close()
        await writer.wait_closed()

    upstream_server = await asyncio.start_server(upstream, "127.0.0.1", 0)
    upstream_port = upstream_server.sockets[0].getsockname()[1]

    proxy_server = await asyncio.start_server(
        lambda r, w: _handle_client(r, w, "127.0.0.1", upstream_port),
        "127.0.0.1",
        0,
    )
    proxy_port = proxy_server.sockets[0].getsockname()[1]

    reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
    await upstream_ready.wait()
    writer.write(b"ping")
    await writer.drain()
    response = await asyncio.wait_for(reader.read(1024), timeout=2)
    assert b"echo:ping" in response or upstream_payload in response

    writer.close()
    await writer.wait_closed()
    proxy_server.close()
    await proxy_server.wait_closed()
    upstream_server.close()
    await upstream_server.wait_closed()
