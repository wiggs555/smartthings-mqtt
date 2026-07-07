"""SmartThings API client wrapper."""

from __future__ import annotations

import logging

from aiohttp import ClientSession
from pysmartthings import SmartThings

_LOGGER = logging.getLogger(__name__)


class SmartThingsClient:
    """Lifecycle wrapper around pysmartthings.SmartThings."""

    def __init__(self, token: str) -> None:
        self._token = token
        self._session: ClientSession | None = None
        self._api: SmartThings | None = None

    @property
    def api(self) -> SmartThings:
        if self._api is None:
            raise RuntimeError("SmartThings client not started")
        return self._api

    async def start(self) -> None:
        self._session = ClientSession()
        self._api = SmartThings(session=self._session)
        self._api.authenticate(self._token)
        _LOGGER.info("SmartThings client authenticated")

    async def stop(self) -> None:
        if self._api is not None:
            await self._api.close()
            self._api = None
        if self._session is not None:
            await self._session.close()
            self._session = None
