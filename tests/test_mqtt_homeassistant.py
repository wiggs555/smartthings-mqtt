"""Tests for Home Assistant MQTT payloads."""

from smartthings_mqtt.mqtt.homeassistant import (
    build_discovery_payloads,
    device_topics,
    discovery_topics,
)


def test_device_topics():
    topics = device_topics("smartthings/tv", "abc-123")
    assert topics["power_state"] == "smartthings/tv/abc-123/power/state"
    assert topics["power_command"] == "smartthings/tv/abc-123/power/set"
    assert topics["volume_state"] == "smartthings/tv/abc-123/volume/state"


def test_discovery_topics():
    topics = discovery_topics("homeassistant", "abc-def-ghi")
    assert topics["power"] == "homeassistant/switch/smartthings_tv_abcdefghi_power/config"
    assert topics["volume"] == "homeassistant/number/smartthings_tv_abcdefghi_volume/config"
    assert topics["source"] == "homeassistant/select/smartthings_tv_abcdefghi_source/config"


def test_build_discovery_payloads():
    topics = device_topics("smartthings/tv", "dev-1")
    payloads = build_discovery_payloads(
        name="Living Room",
        device_id="dev-1",
        topics=topics,
        discovery_prefix="homeassistant",
        source_list=["HDMI1", "HDMI2"],
        model="QN65",
    )
    assert len(payloads) == 4
    kinds = {topic.split("/")[1] for topic, _ in payloads}
    assert kinds == {"switch", "number", "select"}
    power_topic, power_payload = payloads[0]
    assert "switch" in power_topic
    assert power_payload["name"] == "Living Room Power"
    assert power_payload["unique_id"] == "smartthings_mqtt_dev-1_power"
    assert power_payload["state_topic"] == topics["power_state"]
    assert power_payload["command_topic"] == topics["power_command"]
    assert power_payload["device"]["manufacturer"] == "Samsung"
    assert power_payload["device"]["model"] == "QN65"
    source_topic, source_payload = next(
        item for item in payloads if item[0].endswith("_source/config")
    )
    assert "select" in source_topic
    assert source_payload["options"] == ["HDMI1", "HDMI2"]


def test_build_discovery_payloads_without_source():
    topics = device_topics("smartthings/tv", "dev-2")
    payloads = build_discovery_payloads(
        name="Bedroom",
        device_id="dev-2",
        topics=topics,
        discovery_prefix="homeassistant",
    )
    assert len(payloads) == 3
