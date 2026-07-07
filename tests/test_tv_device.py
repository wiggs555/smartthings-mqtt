"""Tests for cloud status parsing."""

from pysmartthings import Attribute, Capability, Status

from smartthings_mqtt.smartthings.tv_device import parse_cloud_status


def _status(value):
    return Status(value=value)


def test_parse_cloud_status():
    components = {
        "main": {
            Capability.SWITCH: {Attribute.SWITCH: _status("on")},
            Capability.AUDIO_VOLUME: {Attribute.VOLUME: _status(42)},
            Capability.AUDIO_MUTE: {Attribute.MUTE: _status("muted")},
            Capability.MEDIA_INPUT_SOURCE: {
                Attribute.INPUT_SOURCE: _status("HDMI1"),
                Attribute.SUPPORTED_INPUT_SOURCES: _status('["HDMI1","HDMI2"]'),
            },
            Capability.TV_CHANNEL: {
                Attribute.TV_CHANNEL: _status("5"),
                Attribute.TV_CHANNEL_NAME: _status("CNN"),
            },
        }
    }
    state = parse_cloud_status(components)
    assert state.power == "on"
    assert state.volume == 42
    assert state.muted is True
    assert state.source == "HDMI1"
    assert state.channel == "5"
    assert state.channel_name == "CNN"
    assert "HDMI1" in state.source_list


def test_tv_state_mqtt_dict():
    from smartthings_mqtt.smartthings.tv_device import TvState

    state = TvState(power="on", volume=50, muted=False, source="HDMI1")
    d = state.as_mqtt_dict()
    assert d["state"] == "on"
    assert d["volume_level"] == 0.5
    assert d["is_volume_muted"] is False
    assert d["source"] == "HDMI1"
