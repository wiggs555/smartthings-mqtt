"""Tests for Home Assistant MQTT payloads."""

from smartthings_mqtt.mqtt.homeassistant import (
    DEFAULT_FEATURES,
    build_discovery_payload,
    device_topics,
    discovery_topic,
)


def test_device_topics():
    topics = device_topics("smartthings/tv", "abc-123")
    assert topics["state"] == "smartthings/tv/abc-123/state"
    assert topics["command"] == "smartthings/tv/abc-123/set"


def test_discovery_topic():
    topic = discovery_topic("homeassistant", "abc-def-ghi")
    assert topic == "homeassistant/media_player/smartthings_tv_abcdefghi/config"


def test_build_discovery_payload():
    topics = device_topics("smartthings/tv", "dev-1")
    topic, payload = build_discovery_payload(
        name="Living Room",
        device_id="dev-1",
        topics=topics,
        discovery_prefix="homeassistant",
        source_list=["HDMI1", "HDMI2"],
        model="QN65",
    )
    assert "media_player" in topic
    assert payload["name"] == "Living Room"
    assert payload["unique_id"] == "smartthings_mqtt_dev-1"
    assert payload["state_topic"] == topics["state"]
    assert payload["command_topic"] == topics["command"]
    assert payload["supported_features"] == DEFAULT_FEATURES
    assert payload["source_list"] == ["HDMI1", "HDMI2"]
    assert payload["device"]["manufacturer"] == "Samsung"
    assert payload["device"]["model"] == "QN65"
