"""aiomqtt client wrapper."""

from __future__ import annotations

import json
import logging
from typing import Any

import aiomqtt

_LOGGER = logging.getLogger(__name__)


class MqttPublisher:
    """Thin wrapper around aiomqtt.Client."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._client: aiomqtt.Client | None = None

    async def __aenter__(self) -> MqttPublisher:
        kwargs: dict[str, Any] = {"hostname": self._host, "port": self._port}
        if self._username:
            kwargs["username"] = self._username
        if self._password:
            kwargs["password"] = self._password
        self._client = aiomqtt.Client(**kwargs)
        await self._client.__aenter__()
        _LOGGER.info("Connected to MQTT broker %s:%s", self._host, self._port)
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._client is not None:
            await self._client.__aexit__(*args)
            self._client = None

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
