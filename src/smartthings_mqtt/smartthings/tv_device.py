"""Cloud-side TV status and command handling."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from pysmartthings import Attribute, Capability, Command, Device, SmartThings

_LOGGER = logging.getLogger(__name__)

DIGITAL_TV = "digitalTv"


@dataclass
class TvState:
    """Normalized TV state for MQTT publishing."""

    power: str = "off"
    volume: int = 0
    muted: bool = False
    source: str = ""
    channel: str = ""
    channel_name: str = ""
    source_list: list[str] = field(default_factory=list)
    online: bool = True

    def as_mqtt_dict(self) -> dict[str, Any]:
        state = "off" if self.power == "off" else "on"
        return {
            "state": state,
            "volume_level": self.volume / 100.0,
            "is_volume_muted": self.muted,
            "source": self.source,
            "media_title": self.channel_name or self.channel,
        }


def _cap_status(
    components: dict[str, dict[Capability | str, dict[Attribute | str, Any]]],
    capability: Capability | str,
    attribute: Attribute | str,
) -> Any:
    main = components.get("main", {})
    cap = main.get(capability, main.get(str(capability), {}))
    if not cap:
        return None
    attr = cap.get(attribute, cap.get(str(attribute)))
    if attr is None:
        return None
    if hasattr(attr, "value"):
        return attr.value
    if isinstance(attr, dict):
        return attr.get("value")
    return attr


def _load_json_list(value: Any) -> list[Any]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    return []


def parse_cloud_status(
    components: dict[str, dict[Capability | str, dict[Attribute | str, Any]]],
) -> TvState:
    """Parse SmartThings device status into TvState."""
    state = TvState()
    switch = _cap_status(components, Capability.SWITCH, Attribute.SWITCH)
    if switch is not None:
        state.power = "on" if str(switch).lower() == "on" else "off"

    volume = _cap_status(components, Capability.AUDIO_VOLUME, Attribute.VOLUME)
    if volume is not None:
        try:
            state.volume = int(float(volume))
        except (TypeError, ValueError):
            state.volume = 0

    mute = _cap_status(components, Capability.AUDIO_MUTE, Attribute.MUTE)
    if mute is not None:
        state.muted = str(mute).lower() in {"muted", "true", "on"}

    source = _cap_status(components, Capability.MEDIA_INPUT_SOURCE, Attribute.INPUT_SOURCE)
    if source is None:
        source = _cap_status(
            components, Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE, Attribute.INPUT_SOURCE
        )
    if source:
        state.source = str(source)

    channel = _cap_status(components, Capability.TV_CHANNEL, Attribute.TV_CHANNEL)
    if channel:
        state.channel = str(channel)
    channel_name = _cap_status(components, Capability.TV_CHANNEL, Attribute.TV_CHANNEL_NAME)
    if channel_name:
        state.channel_name = str(channel_name)

    sources_map = _cap_status(
        components, Capability.MEDIA_INPUT_SOURCE, Attribute.SUPPORTED_INPUT_SOURCES_MAP
    )
    if sources_map is None:
        sources_map = _cap_status(
            components,
            Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE,
            Attribute.SUPPORTED_INPUT_SOURCES_MAP,
        )
    source_list: list[str] = []
    for entry in _load_json_list(sources_map):
        if isinstance(entry, dict):
            sid = entry.get("id", "")
            if str(sid).upper() == "DTV":
                source_list.append(DIGITAL_TV)
            elif sid:
                source_list.append(str(sid))
    if not source_list:
        raw_sources = _cap_status(
            components, Capability.MEDIA_INPUT_SOURCE, Attribute.SUPPORTED_INPUT_SOURCES
        )
        source_list = [str(s) for s in _load_json_list(raw_sources)]
    state.source_list = source_list
    return state


class CloudTvController:
    """Execute TV commands via SmartThings cloud API."""

    def __init__(self, api: SmartThings, device: Device) -> None:
        self._api = api
        self._device = device
        self._capabilities = self._collect_capabilities(device)

    @staticmethod
    def _collect_capabilities(device: Device) -> set[Capability]:
        caps: set[Capability] = set()
        for component in device.components.values():
            for cap in component.capabilities:
                try:
                    caps.add(Capability(cap) if isinstance(cap, str) else cap)
                except ValueError:
                    pass
        return caps

    def has_capability(self, capability: Capability) -> bool:
        return capability in self._capabilities

    async def get_status(self) -> TvState:
        components = await self._api.get_device_status(self._device.device_id)
        return parse_cloud_status(components)

    async def get_health_online(self) -> bool:
        health = await self._api.get_device_health(self._device.device_id)
        return health.state.value == "ONLINE"

    async def _command(
        self,
        capability: Capability,
        command: Command,
        argument: int | str | list[Any] | None = None,
    ) -> None:
        if not self.has_capability(capability):
            _LOGGER.debug(
                "Skipping cloud command %s.%s — capability not present on %s",
                capability,
                command,
                self._device.label,
            )
            return
        try:
            await self._api.execute_device_command(
                self._device.device_id, capability, command, argument=argument
            )
        except Exception as exc:
            _LOGGER.warning(
                "SmartThings command %s.%s failed for %s (%s): %s",
                capability,
                command,
                self._device.label,
                self._device.device_id,
                exc,
            )
            raise

    async def turn_off(self) -> None:
        await self._command(Capability.SWITCH, Command.OFF)

    async def turn_on(self) -> None:
        await self._command(Capability.SWITCH, Command.ON)

    async def set_volume(self, level: int) -> None:
        await self._command(Capability.AUDIO_VOLUME, Command.SET_VOLUME, level)

    async def volume_up(self) -> None:
        await self._command(Capability.AUDIO_VOLUME, Command.VOLUME_UP)

    async def volume_down(self) -> None:
        await self._command(Capability.AUDIO_VOLUME, Command.VOLUME_DOWN)

    async def mute(self, muted: bool) -> None:
        await self._command(
            Capability.AUDIO_MUTE, Command.MUTE if muted else Command.UNMUTE
        )

    async def select_source(self, source: str) -> None:
        cap = (
            Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE
            if self.has_capability(Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE)
            else Capability.MEDIA_INPUT_SOURCE
        )
        await self._command(cap, Command.SET_INPUT_SOURCE, source)

    async def set_channel(self, channel: str) -> None:
        await self._command(Capability.TV_CHANNEL, Command.SET_TV_CHANNEL, channel)

    async def channel_up(self) -> None:
        await self._command(Capability.TV_CHANNEL, Command.CHANNEL_UP)

    async def channel_down(self) -> None:
        await self._command(Capability.TV_CHANNEL, Command.CHANNEL_DOWN)
