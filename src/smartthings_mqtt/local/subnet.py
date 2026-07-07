"""Subnet detection for local TV control."""

from __future__ import annotations

import ipaddress
import socket


def get_local_networks() -> list[ipaddress.IPv4Network]:
    """Return IPv4 networks for local interfaces."""
    networks: list[ipaddress.IPv4Network] = []
    try:
        import netifaces  # optional; not in deps — use stdlib fallback
    except ImportError:
        pass
    else:
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface).get(netifaces.AF_INET, [])
            for entry in addrs:
                try:
                    ip = ipaddress.IPv4Address(entry["addr"])
                    mask = entry.get("netmask")
                    if mask:
                        networks.append(
                            ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)
                        )
                except (ValueError, KeyError):
                    continue
        if networks:
            return networks

    # stdlib fallback: hostname resolution only gives one address
    hostname = socket.gethostname()
    try:
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = ipaddress.IPv4Address(info[4][0])
            if not ip.is_loopback:
                networks.append(ipaddress.IPv4Network(f"{ip}/24", strict=False))
    except OSError:
        pass
    return networks


def same_subnet(host: str, networks: list[ipaddress.IPv4Network] | None = None) -> bool:
    """Return True if host is on a local subnet."""
    try:
        addr = ipaddress.IPv4Address(host)
    except ValueError:
        return False
    if addr.is_loopback:
        return True
    nets = networks if networks is not None else get_local_networks()
    return any(addr in net for net in nets)
