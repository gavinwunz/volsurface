"""Visualization and reporting for the volatility surface.

Provides:
- 3D implied volatility surface plots (k × T × IV)
- Skew term structure (slope vs expiry)
- g(k) butterfly diagnostics per slice
- Surface validation reports in readable format

All plotting uses matplotlib Agg backend (no display required) and is
suitable for CI/headless environments.
"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # Headless-safe
import matplotlib.pyplot as plt
import numpy as np

from volfoundry.arbitrage.checks import (
    ArbitrageCheckResult,
    butterfly_g,
    calendar_monotonicity,
)
from volfoundry.surface.ssvi import (
    SsviParams,
    ssvi_implied_vol,
    ssvi_total_variance,
)
from volfoundry.svi.parameterization import (
    SviParams,
    svi_first_derivative,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global style
# ---------------------------------------------------------------------------

plt.rcParams.update({
    "figure.dpi": 120,
    "savefig.dpi": 150,
    "savefig.bbox": "tight",
    "font.size": 9,
})


# ---------------------------------------------------------------------------
# 3D surface plot
# ---------------------------------------------------------------------------


def plot_3d_surface(
    params: SsviParams,
    T_values: np.ndarray,
    k_min: float = -3.0,
    k_max: float = 3.0,
    n_k: int = 100,
    azimuth: float = -60.0,
    elevation: float = 25.0,
    output_path: Optional[str | Path] = None,
) -> plt.Figure:
    """Plot a 3D implied volatility surface.

    Parameters
    ----------
    params : SsviParams
        SSVI parameters with theta_grid populated.
    T_values : ndarray
        Time to expiry values for each slice (matching theta_grid).
    k_min, k_max : float
        Range of log-moneyness.
    n_k : int
        Number of k grid points.
    azimuth, elevation : float
        3D view angles in degrees.
    output_path : str or Path, optional
        If provided, save the figure to this path.

    Returns
    -------
    matplotlib.figure.Figure
    """
    if params.theta_grid is None:
        raise ValueError("SsviParams.theta_grid must be populated")
    if len(params.theta_grid) != len(T_values):
        raise ValueError(
            f"theta_grid length ({len(params.theta_grid)}) must match "
            f"T_values length ({len(T_values)})"
        )

    k_grid = np.linspace(k_min, k_max, n_k)
    K, T_mesh = np.meshgrid(k_grid, T_values)

    # Compute implied vol surface
    iv_surface = np.zeros_like(K)
    for j, (T_j, theta_j) in enumerate(zip(T_values, params.theta_grid)):
        phi_j = params.phi(float(theta_j))
        iv_surface[j, :] = ssvi_implied_vol(k_grid, float(theta_j), float(phi_j),
                                            params.rho, float(T_j))

    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection="3d")

    surf = ax.plot_surface(K, T_mesh, iv_surface, cmap="viridis",
                           linewidth=0, antialiased=True, alpha=0.9)

    ax.set_xlabel("Log-moneyness k = log(K/F)")
    ax.set_ylabel("Time to expiry T (years)")
    ax.set_zlabel("Implied volatility σ_IV")

    ax.view_init(elevation, azimuth)
    ax.set_title(f"SSVI Implied Volatility Surface (ρ={params.rho:.3f}, "
                 f"η={params.eta:.3f}, λ={params.lamb:.3f})")

    fig.colorbar(surf, ax=ax, shrink=0.5, aspect=10, label="σ_IV")

    if output_path:
        fig.savefig(output_path)
        logger.info(f"3D surface saved to {output_path}")

    return fig


# ---------------------------------------------------------------------------
# Skew term structure
# ---------------------------------------------------------------------------


def plot_skew_term_structure(
    params: SsviParams,
    T_values: np.ndarray,
    k_atm_window: float = 0.1,
    output_path: Optional[str | Path] = None,
) -> plt.Figure:
    """Plot the skew term structure: ATM skew slope vs expiry.

    The ATM skew is computed as the first derivative of implied variance
    w'(k) evaluated at k=0, converted to an implied vol skew per unit of
    log-moneyness: dσ_IV/dk ≈ w'(0) / (2 * sqrt(w(0))).

    Parameters
    ----------
    params : SsviParams
        SSVI parameters with theta_grid populated.
    T_values : ndarray
        Expiry times.
    k_atm_window : float
        Window around k=0 for finite-difference skew estimate (backup).
    output_path : str or Path, optional
        Save path.

    Returns
    -------
    matplotlib.figure.Figure
    """
    if params.theta_grid is None:
        raise ValueError("SsviParams.theta_grid must be populated")

    skew_values = []
    for theta_j, T_j in zip(params.theta_grid, T_values):
        phi_j = params.phi(float(theta_j))
        # Total variance at ATM (k=0)
        w_atm = float(ssvi_total_variance(0.0, float(theta_j), float(phi_j), params.rho))

        # w'(0) analytically from SSVI
        # w(k) = theta/2 * (1 + rho*phi*k + sqrt((phi*k+rho)^2 + (1-rho^2)))
        # w'(k) = theta/2 * (rho*phi + (phi*k+rho)*phi / sqrt((phi*k+rho)^2+(1-rho^2)))
        # At k=0: w'(0) = theta/2 * (rho*phi + rho*phi / sqrt(rho^2+(1-rho^2)))
        #                = theta/2 * (rho*phi + rho*phi) = theta * rho * phi
        wp0 = float(theta_j) * params.rho * phi_j
        # IV skew: sigma = sqrt(w/T), dsigma/dk = w'(k) / (2 * sigma * T)
        if w_atm > 0 and T_j > 0:
            sigma_atm = np.sqrt(w_atm / T_j)
            iv_skew = wp0 / (2.0 * sigma_atm * T_j)
        else:
            iv_skew = 0.0
        skew_values.append(iv_skew)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(T_values, skew_values, "o-", color="steelblue", markersize=6)
    ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.8)
    ax.set_xlabel("Time to expiry T (years)")
    ax.set_ylabel("ATM IV skew dσ_IV/dk|_{k=0}")
    ax.set_title(f"Skew Term Structure (ρ={params.rho:.3f}, "
                 f"η={params.eta:.3f}, λ={params.lamb:.3f})")
    ax.grid(True, alpha=0.3)

    # Annotate with the power-law exponent
    ax.text(0.02, 0.95,
            f"λ = {params.lamb:.3f}\n"
            f"Decay: ~T^{{-λ}}",
            transform=ax.transAxes, va="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.8))

    if output_path:
        fig.savefig(output_path)
        logger.info(f"Skew term structure saved to {output_path}")

    return fig


# ---------------------------------------------------------------------------
# g(k) butterfly diagnostics per slice
# ---------------------------------------------------------------------------


def plot_gk_diagnostics(
    slice_results: list[ArbitrageCheckResult],
    k_grid: Optional[np.ndarray] = None,
    k_min: float = -3.0,
    k_max: float = 3.0,
    n_k: int = 500,
    output_path: Optional[str | Path] = None,
) -> plt.Figure:
    """Plot g(k) butterfly diagnostic for multiple slices.

    Parameters
    ----------
    slice_results : list of ArbitrageCheckResult
        Results from check_slice_arbitrage.
    k_grid : ndarray, optional
        Shared k grid. Generated if None.
    k_min, k_max : float
        Grid range.
    n_k : int
        Grid points.
    output_path : str or Path, optional
        Save path.

    Returns
    -------
    matplotlib.figure.Figure
    """
    if k_grid is None:
        k_grid = np.linspace(k_min, k_max, n_k)

    n_slices = len(slice_results)
    n_cols = min(3, n_slices)
    n_rows = int(np.ceil(n_slices / n_cols))

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(5 * n_cols, 4 * n_rows))
    if n_slices == 1:
        axes = np.array([axes])
    axes = np.atleast_1d(axes).flatten()

    for idx, result in enumerate(slice_results):
        ax = axes[idx]
        g = butterfly_g(k_grid, result.params, result.T)
        ax.plot(k_grid, g, color="steelblue", linewidth=1.2)
        ax.axhline(y=0, color="red", linestyle="--", linewidth=0.8, alpha=0.5)
        ax.fill_between(k_grid, 0, g, where=(g < 0), color="red", alpha=0.2,
                        label="Violation")
        ax.set_xlabel("k = log(K/F)")
        ax.set_ylabel("g(k)")
        status = "✓ PASS" if result.butterfly_passed else "✗ REJECTED"
        color = "green" if result.butterfly_passed else "red"
        ax.set_title(f"{result.slice_id} (T={result.T:.4f}) {status}", color=color)
        ax.grid(True, alpha=0.3)
        if g.min() < 0:
            ax.set_ylim(bottom=min(-0.1, g.min() * 1.2))

    # Hide unused subplots
    for idx in range(n_slices, len(axes)):
        axes[idx].set_visible(False)

    fig.suptitle("Butterfly g(k) Diagnostics", fontsize=13, y=1.01)
    fig.tight_layout()

    if output_path:
        fig.savefig(output_path)
        logger.info(f"g(k) diagnostics saved to {output_path}")

    return fig


# ---------------------------------------------------------------------------
# Cross-section plot: IV smile at multiple expiries
# ---------------------------------------------------------------------------


def plot_iv_smile_cross_section(
    params: SsviParams,
    T_values: np.ndarray,
    k_min: float = -2.0,
    k_max: float = 2.0,
    n_k: int = 200,
    output_path: Optional[str | Path] = None,
) -> plt.Figure:
    """Plot implied volatility smiles across multiple expiries.

    Parameters
    ----------
    params : SsviParams
        SSVI parameters.
    T_values : ndarray
        Expiry times.
    k_min, k_max : float
        Log-moneyness range.
    n_k : int
        Grid points.
    output_path : str or Path, optional
        Save path.

    Returns
    -------
    matplotlib.figure.Figure
    """
    if params.theta_grid is None:
        raise ValueError("SsviParams.theta_grid must be populated")

    k_grid = np.linspace(k_min, k_max, n_k)

    fig, ax = plt.subplots(figsize=(10, 6))

    colors = plt.cm.viridis(np.linspace(0.15, 0.85, len(T_values)))

    for idx, (T_j, theta_j) in enumerate(zip(T_values, params.theta_grid)):
        phi_j = params.phi(float(theta_j))
        iv = ssvi_implied_vol(k_grid, float(theta_j), float(phi_j),
                              params.rho, float(T_j))
        ax.plot(k_grid, iv, color=colors[idx], linewidth=1.5,
                label=f"T={T_j:.3f}")

    ax.set_xlabel("Log-moneyness k = log(K/F)")
    ax.set_ylabel("Implied volatility σ_IV")
    ax.set_title(f"SSVI Implied Volatility Smiles (ρ={params.rho:.3f})")
    ax.legend(loc="best", fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)

    if output_path:
        fig.savefig(output_path)
        logger.info(f"IV smile cross-section saved to {output_path}")

    return fig


# ---------------------------------------------------------------------------
# Validation report writer
# ---------------------------------------------------------------------------


def write_surface_report(
    slice_results: list[ArbitrageCheckResult],
    calendar_passed: Optional[bool],
    calendar_violations: list,
    ssvi_params: Optional[SsviParams] = None,
    title: str = "SVI Surface Validation Report",
    output_path: Optional[str | Path] = None,
) -> str:
    """Write a human-readable surface validation report.

    Parameters
    ----------
    slice_results : list of ArbitrageCheckResult
        Per-slice validation results.
    calendar_passed : bool or None
        Calendar monotonicity check result.
    calendar_violations : list
        Calendar violation details.
    ssvi_params : SsviParams, optional
        SSVI parameters for the surface.
    title : str
        Report title.
    output_path : str or Path, optional
        If provided, write the report to this file.

    Returns
    -------
    str
        Report text.
    """
    lines = []
    lines.append("=" * 72)
    lines.append(title)
    lines.append("=" * 72)
    lines.append("")

    if ssvi_params is not None:
        lines.append("SSVI Parameters")
        lines.append("-" * 40)
        lines.append(f"  ρ (correlation):  {ssvi_params.rho:+.6f}")
        lines.append(f"  η (curvature):     {ssvi_params.eta:.6f}")
        lines.append(f"  λ (power-law):     {ssvi_params.lamb:.6f}")
        if ssvi_params.theta_grid is not None:
            lines.append(f"  n slices:          {len(ssvi_params.theta_grid)}")
            lines.append(f"  theta range:       [{ssvi_params.theta_grid[0]:.4f}, "
                         f"{ssvi_params.theta_grid[-1]:.4f}]")
        lines.append(f"  Lee bound satisfied: {'Yes' if ssvi_params.satisfies_lee_bound() else 'No'}")
        lines.append("")

    # Slice table
    lines.append("Per-Slice No-Arbitrage Results")
    lines.append("-" * 72)
    header = f"  {'Slice':<20s} {'T':>8s} {'Butterfly':>10s} {'min g(k)':>12s} {'BL':>6s}"
    lines.append(header)
    lines.append("  " + "-" * 62)

    n_passed = 0
    n_rejected = 0

    for r in slice_results:
        bf_str = "PASS" if r.butterfly_passed else "FAIL"
        bl_str = "PASS" if r.bl_passed else ("FAIL" if r.bl_passed is not None else "N/A")
        lines.append(
            f"  {r.slice_id:<20s} {r.T:>8.4f} {bf_str:>10s} "
            f"{r.butterfly_min_g:>12.6e} {bl_str:>6s}"
        )
        if r.butterfly_passed:
            n_passed += 1
        else:
            n_rejected += 1

    lines.append("")
    lines.append(f"  Butterfly: {n_passed} passed, {n_rejected} rejected")
    if calendar_passed is not None:
        lines.append(f"  Calendar:  {'PASS' if calendar_passed else 'FAIL'}")
        if calendar_violations:
            lines.append(f"  Calendar violations: {len(calendar_violations)} slice pair(s)")
            for T_i, T_j, _ in calendar_violations:
                lines.append(f"    T={T_i:.4f} → T={T_j:.4f}")
    lines.append("")

    overall = (n_rejected == 0 and (calendar_passed is None or calendar_passed))
    lines.append(f"Overall: {'✓ PASS (arbitrage-free surface)' if overall else '✗ FAIL (arbitrage detected)'}")
    lines.append("")

    report = "\n".join(lines)

    if output_path:
        Path(output_path).write_text(report)
        logger.info(f"Surface report saved to {output_path}")

    return report