"""Generate no-arbitrage diagnostic plots and reports."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from volsurface.arbitrage.checks import (
    ArbitrageCheckResult,
    SliceValidationReport,
    butterfly_g,
)
from volsurface.svi.parameterization import SviParams, svi_total_variance

logger = logging.getLogger(__name__)

# Default output directory
DEFAULT_REPORTS_DIR = Path("reports")


def plot_butterfly_g(
    results: List[ArbitrageCheckResult],
    output_dir: str | Path = DEFAULT_REPORTS_DIR,
    prefix: str = "butterfly_g",
) -> List[Path]:
    """Plot the butterfly g(k) function for each slice.

    Saves one PNG per slice and returns the list of file paths.
    Violations (g(k) < 0) are highlighted in red.

    Parameters
    ----------
    results : list of ArbitrageCheckResult
        Per-slice results from check_slice_arbitrage().
    output_dir : str or Path
        Directory for output plots.
    prefix : str
        Filename prefix.

    Returns
    -------
    list of Path
        Paths to saved plots.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = []

    for i, result in enumerate(results):
        k = np.linspace(result.k_range[0], result.k_range[1], 500)
        g = butterfly_g(k, result.params, result.T)

        fig, ax = plt.subplots(figsize=(8, 5))
        ax.axhline(y=0, color="black", linewidth=0.8, linestyle="--")

        # Color violations red
        viol_mask = g < -1e-12
        if np.any(viol_mask):
            ax.plot(k[viol_mask], g[viol_mask], "r.", markersize=2, label="g(k) < 0")
        ax.plot(k[~viol_mask], g[~viol_mask], "b-", linewidth=0.8, label="g(k) >= 0")

        ax.set_xlabel("Log-moneyness k = log(K/F)")
        ax.set_ylabel("g(k)")
        status = "PASS" if result.butterfly_passed else "REJECTED"
        ax.set_title(f"{result.slice_id} (T={result.T:.4f}) — Butterfly {status}\nmin g(k) = {result.butterfly_min_g:.6e}")
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(True, alpha=0.3)

        fname = f"{prefix}_{result.slice_id.replace('/', '_')}.png"
        fpath = output_dir / fname
        fig.savefig(fpath, dpi=120, bbox_inches="tight")
        plt.close(fig)
        paths.append(fpath)

    return paths


def write_validation_report(
    report: SliceValidationReport,
    output_dir: str | Path = DEFAULT_REPORTS_DIR,
    filename: str = "arbitrage_report.txt",
) -> Path:
    """Write a human-readable validation report to disk.

    Parameters
    ----------
    report : SliceValidationReport
        Validation results from validate_surface().
    output_dir : str or Path
        Output directory.
    filename : str
        Report filename.

    Returns
    -------
    Path
        Path to the written report.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("=" * 60)
    lines.append("No-Arbitrage Validation Report")
    lines.append("=" * 60)
    lines.append(f"Overall: {'PASS' if report.all_passed else 'FAIL'}")
    if report.rejected_slices:
        lines.append(f"Rejected slices: {', '.join(report.rejected_slices)}")
    else:
        lines.append("No slices rejected.")
    lines.append("")

    for result in report.slice_results:
        lines.append("-" * 60)
        lines.append(f"Slice: {result.slice_id}  T={result.T:.6f}")
        lines.append(f"  Butterfly (g(k) >= 0): {'PASS' if result.butterfly_passed else 'REJECTED'}")
        lines.append(f"  Min g(k):              {result.butterfly_min_g:.6e}")
        if result.bl_passed is not None:
            lines.append(f"  Breeden-Litzenberger:   {'PASS' if result.bl_passed else 'REJECTED'}")
        lines.append(f"  k range:               [{result.k_range[0]:.2f}, {result.k_range[1]:.2f}]")
        lines.append(f"  SVI params:            a={result.params.a:.6f}, b={result.params.b:.6f}, "
                     f"rho={result.params.rho:.4f}, m={result.params.m:.4f}, "
                     f"sigma={result.params.sigma:.6f}")
        left = result.params.left_slope
        right = result.params.right_slope
        lines.append(f"  Wing slopes:            left={left:.4f}, right={right:.4f}")

    # Calendar
    if report.calendar_passed is not None:
        lines.append("-" * 60)
        lines.append(f"Calendar monotonicity: {'PASS' if report.calendar_passed else 'FAIL'}")
        if report.calendar_violations:
            for T_i, T_j, k_v in report.calendar_violations:
                lines.append(f"  Violation {T_i:.4f} -> {T_j:.4f}: {len(k_v)} k-points")
    else:
        lines.append("-" * 60)
        lines.append("Calendar: N/A (single slice)")

    lines.append("=" * 60)

    fpath = output_dir / filename
    fpath.write_text("\n".join(lines) + "\n")
    logger.info(f"Validation report written to {fpath}")

    return fpath