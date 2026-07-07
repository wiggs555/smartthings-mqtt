"""Wake-on-LAN helpers."""

from __future__ import annotations

import logging

import aiohttp
from wakeonlan import send_magic_packet

_LOGGER = logging.getLogger(__name__)


def send_wol_direct(mac: str, broadcast: str | None = None) -> None:
    """Send WOL magic packet on local network."""
    if broadcast:
        send_magic_packet(mac, ip_address=broadcast)
    else:
        send_magic_packet(mac)
    _LOGGER.info("Sent WOL magic packet to %s", mac)


async def send_wol_via_relay(wol_url: str, mac: str) -> bool:
    """POST WOL request to relay on TV VLAN."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                wol_url,
                json={"mac": mac},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status < 300:
                    _LOGGER.info("Relay WOL succeeded for %s", mac)
                    return True
                _LOGGER.warning("Relay WOL failed: HTTP %s", resp.status)
    except aiohttp.ClientError as exc:
        _LOGGER.warning("Relay WOL error: %s", exc)
    return False


async def wake_tv(
    mac: str,
    *,
    wol_url: str | None = None,
    wol_broadcast: str | None = None,
    retries: int = 3,
    retry_interval: float = 5.0,
) -> None:
    """Attempt WOL with retries."""
    import asyncio

    for attempt in range(retries):
        if wol_url:
            await send_wol_via_relay(wol_url, mac)
        else:
            send_wol_direct(mac, wol_broadcast)
        if attempt < retries - 1:
            await asyncio.sleep(retry_interval)
