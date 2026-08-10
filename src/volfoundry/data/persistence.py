"""Snapshot persistence layer --- save and load option-chain snapshots.

Features:
- Atomic writes (temp file + rename) --- partial writes are never observed.
- Schema versioning stored in parquet metadata.
- Never overwrites an existing snapshot by default.
- Reproducible metadata (package version, schema version, retrieval timestamp).
"""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from volfoundry._version import __version__
from volfoundry.data.fetcher import Snapshot
from volfoundry.exceptions import PersistenceError

logger = logging.getLogger(__name__)

_CURRENT_SCHEMA_VERSION = 1

DEFAULT_DATA_DIR = Path(os.environ.get("VOLSURFACE_DATA_DIR", "data/snapshots"))


def snapshot_filename(currency: str, timestamp: datetime) -> str:
    """Generate a unique parquet filename for a snapshot.

    Format: ``<CURRENCY>-YYYYMMDDTHHMMSS-<micros>.parquet``
    """
    ts_str = timestamp.strftime("%Y%m%dT%H%M%S")
    micros = f"{timestamp.microsecond:06d}"
    return f"{currency.upper()}-{ts_str}-{micros}.parquet"


def _build_metadata(snapshot: Snapshot) -> dict:
    """Build parquet-level metadata dict for a snapshot."""
    return {
        "volfoundry_schema_version": str(snapshot.schema_version),
        "volfoundry_package_version": __version__,
        "currency": snapshot.currency,
        "retrieval_timestamp": snapshot.timestamp.isoformat(),
    }


def write_snapshot(
    snapshot: Snapshot, data_dir: str | Path | None = None
) -> Path:
    """Persist *snapshot* atomically to a timestamped parquet file.

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

    Raises
    ------
    FileExistsError
        If the target file already exists (never silently overwrites).
    PersistenceError
        On I/O or serialisation errors.
    """
    root = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    root.mkdir(parents=True, exist_ok=True)

    fname = snapshot_filename(snapshot.currency, snapshot.timestamp)
    target_path = root / fname

    if target_path.exists():
        raise FileExistsError(
            f"Snapshot file {target_path} already exists --- refusing to overwrite."
        )

    df = snapshot.to_dataframe()
    metadata = _build_metadata(snapshot)

    # Atomic write: write to a temp file in the same directory,
    # then atomically rename into place.  This prevents partial
    # writes from being observed.
    try:
        fd, tmp_path = tempfile.mkstemp(
            suffix=".parquet", prefix=".tmp_", dir=str(root)
        )
        os.close(fd)
        tmp_file = Path(tmp_path)
        df.to_parquet(tmp_file, index=False)
        tmp_file.rename(target_path)
        logger.info("Wrote snapshot %s (%d rows)", target_path, len(df))
    except OSError as exc:
        if tmp_file.exists():
            tmp_file.unlink(missing_ok=True)
        raise PersistenceError(
            f"Failed to write snapshot to {target_path}: {exc}"
        ) from exc

    # Store metadata via PyArrow's custom metadata by reopening
    # (Parquet metadata is stored in the file footer, so we need
    # to read-write; this is a small file so it's fine.)
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pq.read_table(target_path)
        table = table.replace_schema_metadata(
            {**(table.schema.metadata or {}), **metadata}
        )
        pq.write_table(table, target_path)
    except Exception:
        logger.debug(
            "Could not attach schema metadata to %s (non-critical)", target_path
        )

    return target_path


def _read_metadata(path: Path) -> dict:
    """Read parquet-level metadata from a snapshot file.

    Returns
    -------
    dict
        Metadata fields; empty if unavailable.
    """
    try:
        import pyarrow.parquet as pq

        pf = pq.ParquetFile(path)
        meta = pf.metadata.metadata
        return dict(meta) if meta else {}
    except Exception:
        return {}


def read_snapshot(path: str | Path, validate_schema: bool = True) -> pd.DataFrame:
    """Read a raw snapshot parquet file back into a DataFrame.

    Parameters
    ----------
    path : str or Path
        Path to the parquet file.
    validate_schema : bool
        If True, check that the schema version is known.

    Returns
    -------
    DataFrame

    Raises
    ------
    PersistenceError
        If schema validation fails.
    """
    p = Path(path)
    if not p.exists():
        raise PersistenceError(f"Snapshot file not found: {p}")

    if validate_schema:
        meta = _read_metadata(p)
        # Keys are bytes from pyarrow — try both bytes and str
        schema_ver = meta.get(b"volfoundry_schema_version") or meta.get("volfoundry_schema_version")
        if schema_ver is not None:
            if isinstance(schema_ver, bytes):
                schema_ver = schema_ver.decode("ascii")
            try:
                ver = int(schema_ver)
            except (ValueError, TypeError):
                raise PersistenceError(
                    f"Snapshot {p} has unparseable schema version: {schema_ver!r}"
                )
            if ver > _CURRENT_SCHEMA_VERSION:
                raise PersistenceError(
                    f"Snapshot {p} has schema version {ver}, "
                    f"which is newer than this VolFoundry supports "
                    f"({_CURRENT_SCHEMA_VERSION}). Upgrade VolFoundry or "
                    f"use validate_schema=False."
                )

    return pd.read_parquet(p)


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