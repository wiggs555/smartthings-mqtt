"""Local Samsung TV WebSocket client."""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from pathlib import Path

from samsungtvws.async_remote import SamsungTVWSAsyncRemote
from samsungtvws.remote import RemoteControlCommand

from smartthings_mqtt.local.pairing import token_path
from smartthings_mqtt.smartthings.tv_device import TvState

_LOGGER = logging.getLogger(__name__)

_SOURCE_KEY_MAP = {
    "hdmi1": "KEY_HDMI1",
    "hdmi2": "KEY_HDMI2",
    "hdmi3": "KEY_HDMI3",
    "hdmi4": "KEY_HDMI4",
    "digitaltv": "KEY_TV",
    "tv": "KEY_TV",
    "usb": "KEY_USB",
}


@dataclass(frozen=True)
class LocalEndpoint:
    """Resolved WebSocket connection target."""

    host: str
    port: int
    via_proxy: bool = False


class LocalTvClient:
    """Async wrapper around samsungtvws for one TV."""

    def __init__(
        self,
        device_id: str,
        endpoint: LocalEndpoint,
        token_dir: Path,
        *,
        timeout: float = 10.0,
        key_press_delay: float = 0.3,
    ) -> None:
        self._device_id = device_id
        self._endpoint = endpoint
        self._token_dir = token_dir
        self._timeout = timeout
        self._key_press_delay = key_press_delay
        self._remote: SamsungTVWSAsyncRemote | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected and self._remote is not None and self._remote.is_alive()

    async def connect(self) -> bool:
        """Open WebSocket to TV (or proxy). Token file used for pairing persistence."""
        token_file = str(token_path(self._token_dir, self._device_id))
        self._remote = SamsungTVWSAsyncRemote(
            host=self._endpoint.host,
            port=self._endpoint.port,
            token_file=token_file,
            timeout=self._timeout,
            key_press_delay=self._key_press_delay,
            name="SmartThingsMQTT",
        )
        try:
            await self._remote.open()
            self._connected = True
            _LOGGER.debug(
                "Local WS connected to %s:%s (proxy=%s)",
                self._endpoint.host,
                self._endpoint.port,
                self._endpoint.via_proxy,
            )
            return True
        except Exception as exc:
            _LOGGER.debug("Local WS connect failed for %s: %s", self._device_id, exc)
            self._connected = False
            await self.disconnect()
            return False

    async def disconnect(self) -> None:
        if self._remote is not None:
            try:
                await self._remote.close()
            except Exception:
                pass
        self._remote = None
        self._connected = False

    async def _send_key(self, key: str) -> None:
        if self._remote is None:
            if not await self.connect():
                raise ConnectionError("Local TV not connected")
        assert self._remote is not None
        await self._remote.send_command(
            RemoteControlCommand(
                {
                    "Cmd": "Click",
                    "DataOfCmd": key,
                    "Option": "false",
                    "TypeOfRemote": "SendRemoteKey",
                }
            ),
            key_press_delay=self._key_press_delay,
        )

    async def turn_on(self) -> None:
        await self._send_key("KEY_POWER")

    async def turn_off(self) -> None:
        await self._send_key("KEY_POWER")

    async def enter_art_mode(self) -> None:
        """Enter Frame Art Mode via the art websocket only (never KEY_POWER/Ambient)."""
        import asyncio

        from samsungtvws import SamsungTVWS

        token_file = str(token_path(self._token_dir, self._device_id))

        def _set_artmode() -> None:
            tv = SamsungTVWS(
                host=self._endpoint.host,
                port=self._endpoint.port,
                token_file=token_file,
                timeout=self._timeout,
                name="SmartThingsMQTT",
            )
            art = tv.art()
            try:
                if not art.supported():
                    raise RuntimeError(
                        f"FrameTVSupport is false for {self._endpoint.host}"
                    )
                art.set_artmode("on")
            finally:
                with contextlib.suppress(Exception):
                    tv.close()

        await asyncio.to_thread(_set_artmode)
        _LOGGER.info("Local Art Mode enabled for %s", self._device_id)

    async def volume_up(self) -> None:
        await self._send_key("KEY_VOLUP")

    async def volume_down(self) -> None:
        await self._send_key("KEY_VOLDOWN")

    async def mute(self) -> None:
        await self._send_key("KEY_MUTE")

    async def select_source(self, source: str) -> None:
        key = _SOURCE_KEY_MAP.get(source.lower().replace(" ", ""))
        if key:
            await self._send_key(key)
        else:
            _LOGGER.warning("No local key mapping for source %r", source)

    async def get_state(self) -> TvState | None:
        """Local API has limited state; return minimal on-state when connected."""
        if not self.connected:
            return None
        return TvState(power="on", online=True)
