"""MQTT bridge for a single TV."""

from __future__ import annotations

import json
import logging
from typing import Any

from smartthings_mqtt.mqtt.homeassistant import build_discovery_payload, device_topics
from smartthings_mqtt.mqtt.client import MqttPublisher
from smartthings_mqtt.smartthings.tv_device import TvState
from smartthings_mqtt.transport import TvBridge

_LOGGER = logging.getLogger(__name__)


class TvMqttBridge:
    """Publish TV state and handle commands over MQTT."""

    def __init__(
        self,
        bridge: TvBridge,
        mqtt: MqttPublisher,
        topic_prefix: str,
        discovery_prefix: str,
    ) -> None:
        self._bridge = bridge
        self._mqtt = mqtt
        self._topics = device_topics(topic_prefix, bridge.device_id)
        self._discovery_prefix = discovery_prefix
        self._last_published: dict[str, Any] | None = None

    @property
    def command_topic(self) -> str:
        return self._topics["command"]

    @property
    def device_id(self) -> str:
        return self._bridge.device_id

    async def publish_discovery(self, source_list: list[str] | None = None) -> None:
        model = None
        if self._bridge.device.ocf:
            model = self._bridge.device.ocf.model_number
        topic, payload = build_discovery_payload(
            name=self._bridge.display_name,
            device_id=self._bridge.device_id,
            topics=self._topics,
            discovery_prefix=self._discovery_prefix,
            source_list=source_list,
            model=model,
        )
        await self._mqtt.publish_json(topic, payload, retain=True)
        _LOGGER.info("Published HA discovery for %s", self._bridge.display_name)

    async def remove_discovery(self) -> None:
        from smartthings_mqtt.mqtt.homeassistant import discovery_topic

        topic = discovery_topic(self._discovery_prefix, self._bridge.device_id)
        await self._mqtt.publish(topic, "", retain=True)

    async def publish_availability(self, online: bool) -> None:
        await self._mqtt.publish(
            self._topics["availability"],
            "online" if online else "offline",
            retain=True,
        )

    async def publish_state(self, state: TvState) -> None:
        mqtt_state = state.as_mqtt_dict()
        attrs = {
            "channel": state.channel,
            "channel_name": state.channel_name,
            "transport": self._bridge.transport_mode.value,
        }
        if mqtt_state == self._last_published and not state.source_list:
            return
        self._last_published = dict(mqtt_state)
        await self._mqtt.publish_json(self._topics["state"], mqtt_state, retain=True)
        await self._mqtt.publish_json(self._topics["attributes"], attrs, retain=True)
        if state.source_list:
            await self._mqtt.publish_json(
                self._topics["source_list"], state.source_list, retain=True
            )
        await self.publish_availability(state.online)

    async def handle_command_message(self, payload: bytes) -> None:
        try:
            data = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            _LOGGER.warning("Invalid command payload: %s", exc)
            return
        if not isinstance(data, dict):
            return
        await self._bridge.handle_command(data)
        state = await self._bridge.refresh_state()
        await self.publish_state(state)
