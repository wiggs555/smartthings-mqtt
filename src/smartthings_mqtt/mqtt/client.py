"""aiomqtt client wrapper."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any
from urllib.parse import urlparse

import aiomqtt

_LOGGER = logging.getLogger(__name__)


def format_mqtt_error(exc: aiomqtt.MqttError, host: str, port: int) -> str:
    """Return a user-friendly MQTT error message."""
    message = str(exc)
    auth_markers = ("Not authorized", "Bad username or password", "code:4", "code:5", "code:135")
    if any(marker in message for marker in auth_markers):
        return (
            f"MQTT authentication failed for {host}:{port} ({message}). "
            "Home Assistant's Mosquitto add-on requires a username and password — "
            "set MQTT_USERNAME and MQTT_PASSWORD in .env. Create credentials under "
            "Settings → People → Users, or in the Mosquitto add-on Configuration → logins. "
            "Do not use the reserved usernames 'homeassistant' or 'addons'."
        )
    if "timed out" in message.lower():
        return (
            f"MQTT connection to {host}:{port} timed out ({message}). "
            "Verify the broker is running and reachable from this machine."
        )
    return f"MQTT connection to {host}:{port} failed: {message}"


def is_auth_error(exc: aiomqtt.MqttError) -> bool:
    """Return True if the broker rejected credentials (no point retrying)."""
    message = str(exc)
    return any(
        marker in message
        for marker in ("Not authorized", "Bad username or password", "code:4", "code:5", "code:135")
    )


def warn_if_missing_mqtt_credentials(host: str, username: str | None) -> None:
    """Log a hint when connecting to a remote broker without credentials."""
    if username:
        return
    normalized = normalize_mqtt_host(host)
    if normalized in {"localhost", "127.0.0.1", "::1"}:
        return
    _LOGGER.warning(
        "MQTT_USERNAME is not set but MQTT_HOST is %s. Home Assistant's Mosquitto "
        "add-on requires authentication — add MQTT_USERNAME and MQTT_PASSWORD to .env",
        normalized,
    )


def normalize_mqtt_host(host: str) -> str:
    """Strip URL scheme and path accidentally pasted into MQTT_HOST."""
    host = host.strip()
    if "://" in host:
        parsed = urlparse(host)
        if parsed.hostname:
            return parsed.hostname
    return host.split("/")[0]


async def check_broker_reachable(host: str, port: int, timeout: float) -> str | None:
    """Return an error hint if the broker TCP port is not reachable."""
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()
        return None
    except TimeoutError:
        return (
            f"TCP connection to {host}:{port} timed out after {timeout}s — "
            "check MQTT_HOST/MQTT_PORT, firewall rules, and that the broker is running"
        )
    except OSError as exc:
        return (
            f"TCP connection to {host}:{port} failed ({exc}) — "
            "is the MQTT broker running and reachable from this host?"
        )


class MqttPublisher:
    """Thin wrapper around aiomqtt.Client with connect retry."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str | None = None,
        password: str | None = None,
        *,
        timeout: float = 30.0,
        connect_retry_seconds: float = 5.0,
    ) -> None:
        self._host = normalize_mqtt_host(host)
        self._port = port
        self._username = username or None
        self._password = password or None
        self._timeout = timeout
        self._connect_retry_seconds = connect_retry_seconds
        self._client: aiomqtt.Client | None = None

    def _client_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "hostname": self._host,
            "port": self._port,
            "timeout": self._timeout,
        }
        if self._username:
            kwargs["username"] = self._username
        if self._password:
            kwargs["password"] = self._password
        return kwargs

    async def connect(self) -> None:
        """Connect to the broker, retrying until successful."""
        warn_if_missing_mqtt_credentials(self._host, self._username)
        attempt = 0
        while True:
            attempt += 1
            if self._client is not None:
                with contextlib.suppress(Exception):
                    await self._client.__aexit__(None, None, None)
                self._client = None

            reachability = await check_broker_reachable(
                self._host, self._port, min(self._timeout, 10.0)
            )
            if reachability:
                _LOGGER.warning(
                    "MQTT broker unreachable (attempt %d): %s", attempt, reachability
                )
                await asyncio.sleep(self._connect_retry_seconds)
                continue

            self._client = aiomqtt.Client(**self._client_kwargs())
            try:
                await self._client.__aenter__()
                _LOGGER.info("Connected to MQTT broker %s:%s", self._host, self._port)
                return
            except aiomqtt.MqttError as exc:
                hint = format_mqtt_error(exc, self._host, self._port)
                if is_auth_error(exc):
                    raise aiomqtt.MqttError(hint) from exc
                _LOGGER.warning("MQTT connect attempt %d failed: %s", attempt, hint)
                self._client = None
                await asyncio.sleep(self._connect_retry_seconds)

    async def __aenter__(self) -> MqttPublisher:
        await self.connect()
        return self

    async def disconnect(self) -> None:
        """Disconnect immediately (unblocks an in-flight messages iterator)."""
        if self._client is None:
            return
        client = self._client
        self._client = None
        with contextlib.suppress(Exception):
            await client.__aexit__(None, None, None)

    async def __aexit__(self, *args: object) -> None:
        await self.disconnect()

    @property
    def client(self) -> aiomqtt.Client:
        if self._client is None:
            raise RuntimeError("MQTT client not connected")
        return self._client

    async def publish(
        self,
        topic: str,
        payload: str | bytes,
        *,
        retain: bool = False,
        qos: int = 0,
    ) -> None:
        await self.client.publish(topic, payload, retain=retain, qos=qos)

    async def publish_json(self, topic: str, data: dict[str, Any], *, retain: bool = False) -> None:
        await self.publish(topic, json.dumps(data), retain=retain)
