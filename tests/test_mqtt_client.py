"""Tests for MQTT client helpers."""

import pytest
import aiomqtt

from smartthings_mqtt.mqtt.client import (
    check_broker_reachable,
    format_mqtt_error,
    is_auth_error,
    normalize_mqtt_host,
)


def test_normalize_mqtt_host_strips_scheme():
    assert normalize_mqtt_host("mqtt://192.168.1.10") == "192.168.1.10"
    assert normalize_mqtt_host("  localhost  ") == "localhost"


@pytest.mark.asyncio
async def test_check_broker_unreachable():
    hint = await check_broker_reachable("127.0.0.1", 1, timeout=0.5)
    assert hint is not None
    assert "127.0.0.1:1" in hint


def test_format_mqtt_error_auth_hint():
    exc = aiomqtt.MqttError("[code:135] Not authorized")
    msg = format_mqtt_error(exc, "10.0.1.9", 1883)
    assert "MQTT_USERNAME" in msg
    assert "Home Assistant" in msg


def test_is_auth_error():
    assert is_auth_error(aiomqtt.MqttError("[code:135] Not authorized")) is True
    assert is_auth_error(aiomqtt.MqttError("timed out")) is False
