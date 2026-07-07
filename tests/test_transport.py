"""Tests for local endpoint resolution and subnet detection."""

import ipaddress

from smartthings_mqtt.config import DeviceOverlay, LocalProxyConfig
from smartthings_mqtt.local.subnet import same_subnet
from smartthings_mqtt.transport import resolve_local_endpoint


def test_same_subnet():
    networks = [ipaddress.IPv4Network("192.168.1.0/24")]
    assert same_subnet("192.168.1.50", networks) is True
    assert same_subnet("192.168.2.50", networks) is False


def test_resolve_local_endpoint_direct():
    overlay = DeviceOverlay(ip_address="192.168.1.50", mac_address="aa:bb:cc:dd:ee:ff")
    nets = [ipaddress.IPv4Network("192.168.1.0/24")]
    ep = resolve_local_endpoint(overlay, nets)
    assert ep is not None
    assert ep.host == "192.168.1.50"
    assert ep.via_proxy is False


def test_resolve_local_endpoint_proxy():
    overlay = DeviceOverlay(
        ip_address="192.168.2.116",
        mac_address="aa:bb:cc:dd:ee:ff",
        local_proxy=LocalProxyConfig(host="192.168.2.254", port=8002),
    )
    nets = [ipaddress.IPv4Network("192.168.1.0/24")]
    ep = resolve_local_endpoint(overlay, nets)
    assert ep is not None
    assert ep.host == "192.168.2.254"
    assert ep.via_proxy is True


def test_resolve_local_endpoint_cross_subnet_no_proxy():
    overlay = DeviceOverlay(ip_address="192.168.2.116", mac_address="aa:bb:cc:dd:ee:ff")
    nets = [ipaddress.IPv4Network("192.168.1.0/24")]
    assert resolve_local_endpoint(overlay, nets) is None


def test_resolve_local_endpoint_force_local():
    overlay = DeviceOverlay(
        ip_address="192.168.2.116",
        mac_address="aa:bb:cc:dd:ee:ff",
        force_local=True,
    )
    nets = [ipaddress.IPv4Network("192.168.1.0/24")]
    ep = resolve_local_endpoint(overlay, nets)
    assert ep is not None
    assert ep.host == "192.168.2.116"
