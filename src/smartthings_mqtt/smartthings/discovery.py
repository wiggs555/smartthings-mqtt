"""Discover Samsung TVs from SmartThings device list."""

from __future__ import annotations

import logging

from pysmartthings import Capability, Category, Device

_LOGGER = logging.getLogger(__name__)

def is_tv_device(device: Device) -> bool:
    """Return True if device looks like a Samsung TV."""
    for component in device.components.values():
        if component.manufacturer_category == Category.TELEVISION:
            return True
        cap_names = {str(c) for c in component.capabilities}
        if Capability.SWITCH.value in cap_names and (
            Capability.AUDIO_VOLUME.value in cap_names
            or Capability.MEDIA_INPUT_SOURCE.value in cap_names
            or Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE.value in cap_names
        ):
            return True
    if device.ocf and "tv" in device.ocf.device_type.lower():
        return True
    if device.type.value == "OCF" and device.device_type_name and "TV" in device.device_type_name.upper():
        return True
    return False


def filter_tv_devices(devices: list[Device]) -> list[Device]:
    """Filter SmartThings devices to TVs only."""
    tvs = [d for d in devices if is_tv_device(d)]
    _LOGGER.info("Discovered %d TV(s) from %d SmartThings device(s)", len(tvs), len(devices))
    return tvs
