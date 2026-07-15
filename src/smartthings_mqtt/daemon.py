"""Asyncio daemon orchestration."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

import aiomqtt

from smartthings_mqtt.config import Settings, expand_path, load_device_overlays
from smartthings_mqtt.local.subnet import get_local_networks
from smartthings_mqtt.mqtt.bridge import TvMqttBridge
from smartthings_mqtt.mqtt.client import MqttPublisher
from smartthings_mqtt.smartthings.client import SmartThingsClient
from smartthings_mqtt.smartthings.discovery import filter_tv_devices
from smartthings_mqtt.transport import build_bridge

_LOGGER = logging.getLogger(__name__)


class Daemon:
    """Main daemon coordinating SmartThings, MQTT, and TV bridges."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._st = SmartThingsClient(settings.smartthings_token)
        self._mqtt: MqttPublisher | None = None
        self._bridges: dict[str, TvMqttBridge] = {}
        self._stop = asyncio.Event()
        self._networks = get_local_networks()
        self._overlays = load_device_overlays(expand_path(settings.devices_config))
        settings.local_token_dir.mkdir(parents=True, exist_ok=True)

    async def _discover_and_register(self) -> None:
        assert self._mqtt is not None
        all_devices = await self._st.api.get_devices()
        devices = filter_tv_devices(all_devices)
        if not devices:
            _LOGGER.warning(
                "No Samsung TVs found in SmartThings (%d total device(s)). "
                "Confirm TVs appear in the SmartThings app and your PAT has "
                "r:devices:* scope.",
                len(all_devices),
            )
        current_ids = {d.device_id for d in devices}
        known_ids = set(self._bridges.keys())

        for device in devices:
            if device.device_id in self._bridges:
                continue
            overlay = self._overlays.get(device.device_id)
            tv_bridge = build_bridge(
                self._st.api, device, overlay, self._settings, self._networks
            )
            mqtt_bridge = TvMqttBridge(
                tv_bridge,
                self._mqtt,
                self._settings.mqtt_topic_prefix,
                self._settings.mqtt_discovery_prefix,
            )
            state = await tv_bridge.refresh_state()
            await mqtt_bridge.publish_discovery(state.source_list or None)
            await mqtt_bridge.publish_state(state)
            self._bridges[device.device_id] = mqtt_bridge
            _LOGGER.info("Registered TV: %s", tv_bridge.display_name)

        for removed_id in known_ids - current_ids:
            bridge = self._bridges.pop(removed_id)
            await bridge.remove_discovery()
            _LOGGER.info("Removed TV %s from MQTT", removed_id)

    async def _poll_loop(self) -> None:
        while not self._stop.is_set():
            for bridge in list(self._bridges.values()):
                try:
                    state = await bridge._bridge.refresh_state()  # noqa: SLF001
                    await bridge.publish_state(state)
                except Exception as exc:
                    _LOGGER.warning("Poll failed for %s: %s", bridge.device_id, exc)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self._settings.poll_interval_seconds
                )

    async def _rescan_loop(self) -> None:
        while not self._stop.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self._settings.device_rescan_interval_seconds,
                )
            if self._stop.is_set():
                break
            try:
                await self._discover_and_register()
            except Exception as exc:
                _LOGGER.exception("Device rescan failed: %s", exc)

    async def _command_loop(self) -> None:
        assert self._mqtt is not None
        prefix = self._settings.mqtt_topic_prefix
        topic_filter = f"{prefix}/+/+/set"
        await self._mqtt.client.subscribe(topic_filter)
        _LOGGER.info("Subscribed to commands: %s", topic_filter)
        try:
            async for message in self._mqtt.client.messages:
                if self._stop.is_set():
                    break
                topic = str(message.topic)
                parts = topic.split("/")
                if len(parts) < 4:
                    continue
                device_id = parts[-3]
                entity = parts[-2]
                bridge = self._bridges.get(device_id)
                if bridge is None:
                    _LOGGER.debug("Command for unknown device %s", device_id)
                    continue
                try:
                    await bridge.handle_command_message(entity, message.payload)
                except Exception as exc:
                    _LOGGER.exception(
                        "Command failed for %s/%s: %s", device_id, entity, exc
                    )
        except aiomqtt.MqttError:
            # Disconnect during shutdown unblocks the messages iterator.
            if not self._stop.is_set():
                raise

    async def _local_watch_loop(self) -> None:
        while not self._stop.is_set():
            for bridge in self._bridges.values():
                local = bridge._bridge.local  # noqa: SLF001
                if local is not None and not local.connected:
                    with contextlib.suppress(Exception):
                        await local.connect()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=30)

    async def run(self) -> None:
        await self._st.start()
        try:
            async with MqttPublisher(
                self._settings.mqtt_host,
                self._settings.mqtt_port,
                self._settings.mqtt_username,
                self._settings.mqtt_password,
                timeout=float(self._settings.mqtt_connect_timeout_seconds),
                connect_retry_seconds=float(self._settings.mqtt_connect_retry_seconds),
            ) as mqtt:
                self._mqtt = mqtt
                await self._discover_and_register()
                try:
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(self._poll_loop(), name="poll")
                        tg.create_task(self._rescan_loop(), name="rescan")
                        tg.create_task(self._command_loop(), name="commands")
                        tg.create_task(self._local_watch_loop(), name="local_watch")
                        # Wait here so exiting this block cancels sibling tasks.
                        await self._stop.wait()
                        _LOGGER.info("Shutting down…")
                        # Unblock aiomqtt's messages iterator before cancel.
                        await mqtt.disconnect()
                except* asyncio.CancelledError:
                    pass
        finally:
            self._mqtt = None
            await self._st.stop()
            for bridge in self._bridges.values():
                local = bridge._bridge.local  # noqa: SLF001
                if local is not None:
                    with contextlib.suppress(Exception):
                        await local.disconnect()
            _LOGGER.info("Daemon stopped")

    def request_stop(self) -> None:
        self._stop.set()


def install_signal_handlers(daemon: Daemon, loop: asyncio.AbstractEventLoop) -> None:
    """Register SIGINT/SIGTERM handlers."""

    def _handler() -> None:
        _LOGGER.info("Shutdown signal received")
        daemon.request_stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _handler)


async def run_daemon(settings: Settings) -> None:
    """Entry point for running the daemon."""
    daemon = Daemon(settings)
    loop = asyncio.get_running_loop()
    install_signal_handlers(daemon, loop)
    try:
        await daemon.run()
    except asyncio.CancelledError:
        _LOGGER.info("Daemon stopped")
    except aiomqtt.MqttError as exc:
        _LOGGER.error(
            "MQTT error: %s — verify MQTT_HOST=%s MQTT_PORT=%s and that your broker "
            "is running (use the Home Assistant broker IP if not on localhost)",
            exc,
            settings.mqtt_host,
            settings.mqtt_port,
        )
        raise
