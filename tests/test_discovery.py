"""Tests for TV discovery filtering."""

from pysmartthings import Capability, Category, Component, Device, DeviceType

from smartthings_mqtt.smartthings.discovery import filter_tv_devices, is_tv_device


def _make_device(
    *,
    category: Category | str = Category.LIGHT,
    capabilities: list[str] | None = None,
    device_type_name: str | None = None,
) -> Device:
    caps = capabilities or ["switch"]
    component = Component(
        id="main",
        capabilities=caps,
        manufacturer_category=category,
        label=None,
        user_category=None,
    )
    return Device(
        device_id="test-device-id",
        name="Test Device",
        label="Test Label",
        location_id="loc-1",
        type=DeviceType.OCF,
        components={"main": component},
        device_type_name=device_type_name,
    )


def test_is_tv_by_category():
    device = _make_device(category=Category.TELEVISION)
    assert is_tv_device(device) is True


def test_is_tv_by_capabilities():
    device = _make_device(
        category=Category.OTHER,
        capabilities=["switch", "audioVolume", "mediaInputSource"],
    )
    assert is_tv_device(device) is True


def test_is_not_tv():
    device = _make_device(category=Category.LIGHT, capabilities=["switch"])
    assert is_tv_device(device) is False


def test_filter_tv_devices():
    tv = _make_device(category=Category.TELEVISION)
    light = _make_device(category=Category.LIGHT)
    result = filter_tv_devices([tv, light])
    assert len(result) == 1
    assert result[0].device_id == "test-device-id"


def test_is_tv_by_device_type_name():
    device = _make_device(
        category=Category.OTHER,
        capabilities=["switch"],
        device_type_name="Samsung OCF TV",
    )
    assert is_tv_device(device) is True
