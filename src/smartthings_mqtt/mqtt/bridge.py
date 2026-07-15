"""MQTT bridge for a single TV."""

from __future__ import annotations

import logging
from typing import Any

from smartthings_mqtt.mqtt.homeassistant import (
    build_discovery_payloads,
    device_topics,
    discovery_topics,
)
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
        self._has_source_entity = False

    @property
    def device_id(self) -> str:
        return self._bridge.device_id

    async def publish_discovery(self, source_list: list[str] | None = None) -> None:
        model = None
        if self._bridge.device.ocf:
            model = self._bridge.device.ocf.model_number
        payloads = build_discovery_payloads(
            name=self._bridge.display_name,
            device_id=self._bridge.device_id,
            topics=self._topics,
            discovery_prefix=self._discovery_prefix,
            source_list=source_list,
            model=model,
        )
        self._has_source_entity = source_list is not None and len(source_list) > 0
        for topic, payload in payloads:
            await self._mqtt.publish_json(topic, payload, retain=True)
        _LOGGER.info(
            "Published HA discovery for %s (%d entities)",
            self._bridge.display_name,
            len(payloads),
        )

    async def remove_discovery(self) -> None:
        topics = discovery_topics(self._discovery_prefix, self._bridge.device_id)
        for topic in topics.values():
            await self._mqtt.publish(topic, "", retain=True)

    async def publish_availability(self, online: bool) -> None:
        await self._mqtt.publish(
            self._topics["availability"],
            "online" if online else "offline",
            retain=True,
        )

    async def publish_state(self, state: TvState) -> None:
        mqtt_state = {
            "power": "ON" if state.power == "on" else "OFF",
            "volume": str(state.volume),
            "mute": "ON" if state.muted else "OFF",
            "source": state.source,
        }
        attrs = {
            "channel": state.channel,
            "channel_name": state.channel_name,
            "transport": self._bridge.transport_mode.value,
        }
        if mqtt_state == self._last_published and not state.source_list:
            return
        self._last_published = dict(mqtt_state)
        await self._mqtt.publish(
            self._topics["power_state"], mqtt_state["power"], retain=True
        )
        await self._mqtt.publish(
            self._topics["volume_state"], mqtt_state["volume"], retain=True
        )
        await self._mqtt.publish(
            self._topics["mute_state"], mqtt_state["mute"], retain=True
        )
        if state.source or self._has_source_entity:
            await self._mqtt.publish(
                self._topics["source_state"], mqtt_state["source"], retain=True
            )
        await self._mqtt.publish_json(self._topics["attributes"], attrs, retain=True)
        await self.publish_availability(state.online)

    async def handle_command_message(self, entity: str, payload: bytes) -> None:
        value = payload.decode("utf-8").strip()
        if not value:
            return
        try:
            if entity == "power":
                if value.upper() == "ON":
                    await self._bridge.turn_on()
                elif value.upper() == "OFF":
                    await self._bridge.turn_off()
            elif entity == "volume":
                try:
                    await self._bridge.set_volume(
                        max(0, min(100, int(float(value))))
                    )
                except ValueError:
                    _LOGGER.warning("Invalid volume command: %s", value)
                    return
            elif entity == "mute":
                await self._bridge.set_mute(value.upper() == "ON")
            elif entity == "source":
                await self._bridge.select_source(value)
            else:
                _LOGGER.debug("Unknown entity command %s", entity)
                return
        except Exception as exc:
            _LOGGER.warning(
                "Command %s=%s failed for %s: %s",
                entity,
                value,
                self._bridge.display_name,
                exc,
            )
            return
        try:
            state = await self._bridge.refresh_state()
            await self.publish_state(state)
        except Exception as exc:
            _LOGGER.warning(
                "Failed to refresh state after %s command for %s: %s",
                entity,
                self._bridge.display_name,
                exc,
            )
