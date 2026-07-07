"""Per-TV transport routing: local-first, cloud fallback."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from pysmartthings import Device, SmartThings

from smartthings_mqtt.config import DeviceOverlay, Settings
from smartthings_mqtt.local.client import LocalEndpoint, LocalTvClient
from smartthings_mqtt.local.subnet import get_local_networks, same_subnet
from smartthings_mqtt.local.wol import wake_tv
from smartthings_mqtt.smartthings.tv_device import CloudTvController, TvState

_LOGGER = logging.getLogger(__name__)


class TransportMode(StrEnum):
    LOCAL_DIRECT = "local-direct"
    LOCAL_PROXY = "local-proxy"
    CLOUD = "cloud"


def resolve_local_endpoint(
    overlay: DeviceOverlay,
    networks: list | None = None,
) -> LocalEndpoint | None:
    """Resolve WebSocket endpoint per plan logic."""
    if overlay.local_proxy:
        return LocalEndpoint(
            host=overlay.local_proxy.host,
            port=overlay.local_proxy.port,
            via_proxy=True,
        )
    nets = networks if networks is not None else get_local_networks()
    if overlay.force_local or same_subnet(overlay.ip_address, nets):
        return LocalEndpoint(host=overlay.ip_address, port=overlay.port, via_proxy=False)
    return None


@dataclass
class TvBridge:
    """Combined cloud + optional local control for one TV."""

    device: Device
    overlay: DeviceOverlay | None
    cloud: CloudTvController
    settings: Settings
    local: LocalTvClient | None = None
    last_state: TvState | None = None
    transport_mode: TransportMode = TransportMode.CLOUD

    @property
    def device_id(self) -> str:
        return self.device.device_id

    @property
    def display_name(self) -> str:
        if self.overlay and self.overlay.name:
            return self.overlay.name
        return self.device.label or self.device.name

    def setup_local(self, networks: list | None = None) -> None:
        if not self.settings.local_enabled or self.overlay is None:
            return
        endpoint = resolve_local_endpoint(self.overlay, networks)
        if endpoint is None:
            _LOGGER.info(
                "No local path for %s (%s) — cloud only",
                self.display_name,
                self.overlay.ip_address,
            )
            return
        self.local = LocalTvClient(
            self.device_id,
            endpoint,
            self.settings.local_token_dir,
            timeout=float(self.settings.local_connect_timeout_seconds),
        )
        self.transport_mode = (
            TransportMode.LOCAL_PROXY if endpoint.via_proxy else TransportMode.LOCAL_DIRECT
        )

    async def refresh_state(self) -> TvState:
        state: TvState | None = None
        if self.local is not None:
            if not self.local.connected:
                await self.local.connect()
            if self.local.connected:
                local_state = await self.local.get_state()
                if local_state:
                    state = local_state
        if state is None:
            self.transport_mode = TransportMode.CLOUD
            try:
                online = await self.cloud.get_health_online()
                if not online:
                    self.last_state = TvState(power="off", online=False)
                    return self.last_state
                state = await self.cloud.get_status()
            except Exception as exc:
                _LOGGER.warning("Cloud status failed for %s: %s", self.display_name, exc)
                state = self.last_state or TvState(online=False)
        else:
            try:
                cloud = await self.cloud.get_status()
                state.volume = cloud.volume
                state.muted = cloud.muted
                state.source = cloud.source or state.source
                state.source_list = cloud.source_list
                state.channel = cloud.channel
                state.channel_name = cloud.channel_name
            except Exception:
                pass
        self.last_state = state
        return state

    async def _try_local(self, action: str, method_name: str) -> bool:
        if self.local is None:
            return False
        try:
            if not self.local.connected:
                await self.local.connect()
            if self.local.connected:
                method = getattr(self.local, method_name)
                await method()
                _LOGGER.debug("%s via %s", action, self.transport_mode)
                return True
        except Exception as exc:
            _LOGGER.debug("Local %s failed (%s), trying cloud", action, exc)
        return False

    async def turn_off(self) -> None:
        if await self._try_local("turn_off", "turn_off"):
            return
        self.transport_mode = TransportMode.CLOUD
        await self.cloud.turn_off()

    async def turn_on(self) -> None:
        overlay = self.overlay
        if overlay and overlay.mac_address:
            wol_url = None
            wol_broadcast = overlay.wol_broadcast
            if overlay.local_proxy and overlay.local_proxy.wol_url:
                wol_url = overlay.local_proxy.wol_url
            await wake_tv(
                overlay.mac_address,
                wol_url=wol_url,
                wol_broadcast=wol_broadcast,
                retries=self.settings.wol_retries,
                retry_interval=float(self.settings.wol_retry_interval_seconds),
            )
        if await self._try_local("turn_on", "turn_on"):
            return
        self.transport_mode = TransportMode.CLOUD
        await self.cloud.turn_on()

    async def set_volume(self, level: int) -> None:
        if self.local is not None and self.local.connected:
            await self._volume_steps(level)
            _LOGGER.debug("volume via %s", self.transport_mode)
            return
        self.transport_mode = TransportMode.CLOUD
        await self.cloud.set_volume(level)

    async def _volume_steps(self, target: int) -> Any:
        """Approximate volume set via key presses (local API limitation)."""
        assert self.local is not None
        current = (self.last_state.volume if self.last_state else 0)
        diff = target - current
        if diff > 0:
            for _ in range(min(diff // 2 + 1, 30)):
                await self.local.volume_up()
        elif diff < 0:
            for _ in range(min(abs(diff) // 2 + 1, 30)):
                await self.local.volume_down()

    async def set_mute(self, muted: bool) -> None:
        if muted and await self._try_local("mute", "mute"):
            return
        self.transport_mode = TransportMode.CLOUD
        await self.cloud.mute(muted)

    async def select_source(self, source: str) -> None:
        if self.local is not None and self.local.connected:
            await self.local.select_source(source)
            _LOGGER.debug("select_source via %s", self.transport_mode)
            return
        self.transport_mode = TransportMode.CLOUD
        await self.cloud.select_source(source)

    async def handle_command(self, payload: dict[str, Any]) -> None:
        """Handle Home Assistant media_player MQTT command JSON."""
        if "state" in payload:
            state = str(payload["state"]).upper()
            if state == "ON":
                await self.turn_on()
            elif state == "OFF":
                await self.turn_off()
        if "volume_level" in payload:
            level = int(float(payload["volume_level"]) * 100)
            await self.set_volume(max(0, min(100, level)))
        if "volume" in payload:
            await self.set_volume(max(0, min(100, int(payload["volume"]))))
        if "is_volume_muted" in payload:
            await self.set_mute(bool(payload["is_volume_muted"]))
        media_type = payload.get("media_content_type", "")
        media_id = payload.get("media_content_id", "")
        if media_id and media_type in {"source", "channel", ""}:
            await self.select_source(str(media_id))


def build_bridge(
    api: SmartThings,
    device: Device,
    overlay: DeviceOverlay | None,
    settings: Settings,
    networks: list | None = None,
) -> TvBridge:
    bridge = TvBridge(
        device=device,
        overlay=overlay,
        cloud=CloudTvController(api, device),
        settings=settings,
    )
    bridge.setup_local(networks)
    return bridge
