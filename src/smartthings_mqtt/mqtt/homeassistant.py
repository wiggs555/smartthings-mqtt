"""Home Assistant MQTT discovery payloads."""

from __future__ import annotations

from typing import Any

EntityDiscovery = tuple[str, dict[str, Any]]


def _safe_id(device_id: str) -> str:
    return device_id.replace("-", "")


def _device_block(
    *,
    name: str,
    device_id: str,
    model: str | None = None,
) -> dict[str, Any]:
    return {
        "identifiers": [f"smartthings_{device_id}"],
        "name": name,
        "manufacturer": "Samsung",
        "model": model or "SmartThings TV",
    }


def device_topics(prefix: str, device_id: str) -> dict[str, str]:
    base = f"{prefix}/{device_id}"
    return {
        "availability": f"{base}/availability",
        "power_state": f"{base}/power/state",
        "power_command": f"{base}/power/set",
        "volume_state": f"{base}/volume/state",
        "volume_command": f"{base}/volume/set",
        "mute_state": f"{base}/mute/state",
        "mute_command": f"{base}/mute/set",
        "source_state": f"{base}/source/state",
        "source_command": f"{base}/source/set",
        "attributes": f"{base}/attributes",
    }


def discovery_topics(discovery_prefix: str, device_id: str) -> dict[str, str]:
    """Return HA discovery config topics keyed by entity kind."""
    safe = _safe_id(device_id)
    return {
        "power": f"{discovery_prefix}/switch/smartthings_tv_{safe}_power/config",
        "volume": f"{discovery_prefix}/number/smartthings_tv_{safe}_volume/config",
        "mute": f"{discovery_prefix}/switch/smartthings_tv_{safe}_mute/config",
        "source": f"{discovery_prefix}/select/smartthings_tv_{safe}_source/config",
    }


def build_discovery_payloads(
    *,
    name: str,
    device_id: str,
    topics: dict[str, str],
    discovery_prefix: str,
    source_list: list[str] | None = None,
    model: str | None = None,
) -> list[EntityDiscovery]:
    """Return HA MQTT discovery messages for supported entity platforms."""
    device = _device_block(name=name, device_id=device_id, model=model)
    discovery = discovery_topics(discovery_prefix, device_id)
    availability = {
        "availability_topic": topics["availability"],
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    payloads: list[EntityDiscovery] = [
        (
            discovery["power"],
            {
                "name": f"{name} Power",
                "unique_id": f"smartthings_mqtt_{device_id}_power",
                "state_topic": topics["power_state"],
                "command_topic": topics["power_command"],
                "payload_on": "ON",
                "payload_off": "OFF",
                "state_on": "ON",
                "state_off": "OFF",
                "icon": "mdi:television",
                "device": device,
                **availability,
            },
        ),
        (
            discovery["volume"],
            {
                "name": f"{name} Volume",
                "unique_id": f"smartthings_mqtt_{device_id}_volume",
                "state_topic": topics["volume_state"],
                "command_topic": topics["volume_command"],
                "min": 0,
                "max": 100,
                "step": 1,
                "mode": "slider",
                "device": device,
                **availability,
            },
        ),
        (
            discovery["mute"],
            {
                "name": f"{name} Mute",
                "unique_id": f"smartthings_mqtt_{device_id}_mute",
                "state_topic": topics["mute_state"],
                "command_topic": topics["mute_command"],
                "payload_on": "ON",
                "payload_off": "OFF",
                "state_on": "ON",
                "state_off": "OFF",
                "device": device,
                **availability,
            },
        ),
    ]
    if source_list:
        payloads.append(
            (
                discovery["source"],
                {
                    "name": f"{name} Source",
                    "unique_id": f"smartthings_mqtt_{device_id}_source",
                    "state_topic": topics["source_state"],
                    "command_topic": topics["source_command"],
                    "options": source_list,
                    "device": device,
                    **availability,
                },
            )
        )
    return payloads
