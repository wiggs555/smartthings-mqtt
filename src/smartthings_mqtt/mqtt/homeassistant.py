"""Home Assistant MQTT discovery payloads."""

from __future__ import annotations

from typing import Any

# homeassistant.components.media_player.MediaPlayerEntityFeature
SUPPORT_TURN_ON = 128
SUPPORT_TURN_OFF = 64
SUPPORT_VOLUME_SET = 4
SUPPORT_VOLUME_MUTE = 8
SUPPORT_SELECT_SOURCE = 512
SUPPORT_VOLUME_STEP = 1024

DEFAULT_FEATURES = (
    SUPPORT_TURN_ON
    | SUPPORT_TURN_OFF
    | SUPPORT_VOLUME_SET
    | SUPPORT_VOLUME_MUTE
    | SUPPORT_SELECT_SOURCE
    | SUPPORT_VOLUME_STEP
)


def discovery_topic(discovery_prefix: str, device_id: str) -> str:
    safe_id = device_id.replace("-", "")
    return f"{discovery_prefix}/media_player/smartthings_tv_{safe_id}/config"


def device_topics(prefix: str, device_id: str) -> dict[str, str]:
    base = f"{prefix}/{device_id}"
    return {
        "availability": f"{base}/availability",
        "state": f"{base}/state",
        "command": f"{base}/set",
        "source_list": f"{base}/source_list",
        "attributes": f"{base}/attributes",
    }


def build_discovery_payload(
    *,
    name: str,
    device_id: str,
    topics: dict[str, str],
    discovery_prefix: str,
    source_list: list[str] | None = None,
    model: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return (topic, payload) for HA MQTT discovery."""
    topic = discovery_topic(discovery_prefix, device_id)
    payload: dict[str, Any] = {
        "name": name,
        "unique_id": f"smartthings_mqtt_{device_id}",
        "availability_topic": topics["availability"],
        "payload_available": "online",
        "payload_not_available": "offline",
        "state_topic": topics["state"],
        "command_topic": topics["command"],
        "json_attributes_topic": topics["attributes"],
        "supported_features": DEFAULT_FEATURES,
        "device": {
            "identifiers": [f"smartthings_{device_id}"],
            "name": name,
            "manufacturer": "Samsung",
            "model": model or "SmartThings TV",
            "via_device": "smartthings_mqtt",
        },
    }
    if source_list:
        payload["source_list"] = source_list
    return topic, payload
