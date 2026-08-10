"""Snapshot persistence layer — save raw option-chain data to parquet.

Every snapshot is written to a timestamped, uniquely-named parquet file.
Files are NEVER overwritten.  The layer also supports reading back raw
snapshot files for downstream processing.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from volsurface.data.fetcher import Snapshot

logger = logging.getLogger(__name__)

# Default location for raw data snapshots.  Can be overridden via env var.
DEFAULT_DATA_DIR = Path(os.environ.get("VOLSURFACE_DATA_DIR", "data/snapshots"))


def snapshot_filename(currency: str, timestamp: datetime) -> str:
    """Generate a unique parquet filename for a snapshot.

    Format: ``<CURRENCY>-YYYYMMDDTHHMMSS-<micros>.parquet``
    """
    ts_str = timestamp.strftime("%Y%m%dT%H%M%S")
    micros = f"{timestamp.microsecond:06d}"
    return f"{currency.upper()}-{ts_str}-{micros}.parquet"


def write_snapshot(
    snapshot: Snapshot, data_dir: str | Path | None = None
) -> Path:
    """Persist *snapshot* to a timestamped parquet file.

    Parameters
    ----------
    snapshot : Snapshot
        The snapshot object to persist.
    data_dir : str or Path, optional
        Directory to write to.  Defaults to ``data/snapshots/``.

    Returns
    -------
    Path
        Path to the written parquet file.
    """
    root = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    root.mkdir(parents=True, exist_ok=True)

    fname = snapshot_filename(snapshot.currency, snapshot.timestamp)
    path = root / fname

    if path.exists():
        raise FileExistsError(
            f"Snapshot file {path} already exists — refusing to overwrite."
        )

    df = snapshot.to_dataframe()
    df.to_parquet(path, index=False)
    logger.info("Wrote snapshot %s (%d rows)", path, len(df))
    return path


def read_snapshot(path: str | Path) -> pd.DataFrame:
    """Read a raw snapshot parquet file back into a DataFrame."""
    return pd.read_parquet(path)


def list_snapshots(
    currency: str | None = None, data_dir: str | Path | None = None
) -> list[Path]:
    """List all snapshot files, optionally filtered by currency."""
    root = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    if not root.exists():
        return []
    pattern = f"{currency.upper()}-*" if currency else "*-*"
    files = sorted(root.glob(f"{pattern}.parquet"))
    return files


def load_snapshot(
    currency: str | None = None,
    latest: bool = True,
    data_dir: str | Path | None = None,
) -> pd.DataFrame | None:
    """Load the latest (or all) snapshot(s) for a currency.

    Parameters
    ----------
    currency : str, optional
        Filter to this currency (e.g. ``"BTC"``).
    latest : bool
        If True, return only the most recent snapshot.
    data_dir : str or Path, optional
        Directory to read from.

    Returns
    -------
    DataFrame or None
    """
    files = list_snapshots(currency=currency, data_dir=data_dir)
    if not files:
        return None
    if latest:
        return read_snapshot(files[-1])
    return pd.concat([read_snapshot(f) for f in files], ignore_index=True)