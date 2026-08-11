"""High-level Deribit client for the VolFoundry public API.

Provides ``DeribitClient``, a user-facing wrapper around the existing
``DeribitPublicClient`` that returns a ``Snapshot`` suitable for feeding
directly into ``SurfaceBuilder.fit()``.

Importing this module does **not** make network calls.  All network
activity happens through explicit method calls.
"""

from __future__ import annotations

import logging

from volfoundry.data.fetcher import (
    DeribitPublicClient,
    Snapshot,
)

logger = logging.getLogger(__name__)


class DeribitClient:
    """High-level client for fetching Deribit option-chain snapshots.

    Thin wrapper around ``DeribitPublicClient`` that provides the public
    API entry point expected by ``SurfaceBuilder``.

    Parameters
    ----------
    timeout : int
        HTTP connect/read timeout in seconds (default 30).

    Example
    -------
    >>> from volfoundry import DeribitClient, SurfaceBuilder
    >>> snapshot = DeribitClient().fetch("BTC")
    >>> result = SurfaceBuilder().fit(snapshot)
    >>> print(result.surface.iv(strike=70_000, maturity=30 / 365.25))
    """

    def __init__(
        self,
        connect_timeout: float = 10,
        read_timeout: float = 30,
    ) -> None:
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._client: DeribitPublicClient | None = None

    def _get_client(self) -> DeribitPublicClient:
        """Lazily create the underlying client (reuses session)."""
        if self._client is None:
            self._client = DeribitPublicClient(
                connect_timeout=self._connect_timeout,
                read_timeout=self._read_timeout,
            )
        return self._client

    def fetch(self, currency: str) -> Snapshot:
        """Fetch a full option-chain snapshot for *currency*.

        Parameters
        ----------
        currency : str
            Underlying currency, e.g. ``"BTC"`` or ``"ETH"``.

        Returns
        -------
        Snapshot
            Structured snapshot containing all quotes, metadata, and a
            ``cleaning_report`` attribute.

        Raises
        ------
        MarketDataError
            On JSON-RPC errors, HTTP failures, or empty instrument lists.
            Never returns an empty snapshot as a proxy for failure.
        """
        return self._get_client().fetch_snapshot(currency.upper())
