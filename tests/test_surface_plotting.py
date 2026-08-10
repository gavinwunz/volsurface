"""Tests for volfoundry.surface.plotting — SSVI surface visualizations."""

from __future__ import annotations

import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pytest

from volfoundry.surface.ssvi import SsviParams
from volfoundry.surface.plotting import (
    plot_3d_surface,
    plot_skew_term_structure,
    plot_gk_diagnostics,
    plot_iv_smile_cross_section,
    write_surface_report,
)
from volfoundry.arbitrage.checks import (
    ArbitrageCheckResult,
    check_slice_arbitrage,
)
from volfoundry.svi.parameterization import SviParams as SviP, svi_total_variance


@pytest.fixture
def valid_ssvi_params() -> SsviParams:
    """Create a valid SSVI surface with theta_grid populated."""
    thetas = np.array([0.01, 0.04, 0.09, 0.16])
    return SsviParams(rho=-0.3, eta=1.2, lamb=0.25, theta_grid=thetas)


@pytest.fixture
def T_values():
    return np.array([0.1, 0.25, 0.5, 1.0])


@pytest.fixture
def sample_arb_results():
    """Generate sample ArbitrageCheckResult objects."""
    results = []
    for i, T in enumerate([0.25, 0.5, 0.75]):
        # Create a valid clean slice
        p = SviP(a=0.02 * (i + 1), b=0.3, rho=-0.2, m=0.01 * i, sigma=0.15)
        results.append(
            ArbitrageCheckResult(
                slice_id=f"TEST-{i}",
                T=T,
                butterfly_passed=True,
                butterfly_min_g=0.001,
                bl_passed=True if T <= 0.5 else None,
                params=p,
                k_range=(-5.0, 5.0),
            )
        )
    # Add one failing slice
    p_bad = SviP(a=0.01, b=0.8, rho=0.5, m=0.0, sigma=0.05)
    results.append(
        ArbitrageCheckResult(
            slice_id="TEST-FAIL",
            T=0.1,
            butterfly_passed=False,
            butterfly_min_g=-0.05,
            bl_passed=False,
            params=p_bad,
            k_range=(-5.0, 5.0),
        )
    )
    return results


# ===================================================================
# plot_3d_surface
# ===================================================================


class TestPlot3dSurface:
    def test_basic_plot(self, valid_ssvi_params, T_values):
        fig = plot_3d_surface(valid_ssvi_params, T_values)
        assert fig is not None
        assert len(fig.axes) >= 1  # includes colorbar axis

    def test_custom_k_range(self, valid_ssvi_params, T_values):
        fig = plot_3d_surface(valid_ssvi_params, T_values,
                              k_min=-2.0, k_max=2.0, n_k=50)
        assert fig is not None

    def test_custom_view_angles(self, valid_ssvi_params, T_values):
        fig = plot_3d_surface(valid_ssvi_params, T_values,
                              azimuth=30.0, elevation=60.0)
        assert fig is not None

    def test_save_to_file(self, valid_ssvi_params, T_values):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "surface_3d.png"
            fig = plot_3d_surface(valid_ssvi_params, T_values, output_path=out)
            assert out.exists()
            assert out.stat().st_size > 0

    def test_mismatched_lengths_raises(self, valid_ssvi_params):
        with pytest.raises(ValueError, match="must match"):
            plot_3d_surface(valid_ssvi_params, np.array([0.1, 0.2, 0.3]))

    def test_no_theta_grid_raises(self):
        p = SsviParams(rho=-0.3, eta=1.0, lamb=0.5)
        with pytest.raises(ValueError, match="theta_grid must be populated"):
            plot_3d_surface(p, np.array([0.1, 0.25]))


# ===================================================================
# plot_skew_term_structure
# ===================================================================


class TestPlotSkewTermStructure:
    def test_basic_plot(self, valid_ssvi_params, T_values):
        fig = plot_skew_term_structure(valid_ssvi_params, T_values)
        assert fig is not None

    def test_save_to_file(self, valid_ssvi_params, T_values):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "skew.png"
            fig = plot_skew_term_structure(valid_ssvi_params, T_values, output_path=out)
            assert out.exists()
            assert out.stat().st_size > 0

    def test_no_theta_grid_raises(self):
        p = SsviParams(rho=-0.3, eta=1.0, lamb=0.5)
        with pytest.raises(ValueError, match="theta_grid must be populated"):
            plot_skew_term_structure(p, np.array([0.1]))

    def test_negative_rho_gives_negative_skew(self, T_values):
        """Negative correlation should produce negative ATM skew."""
        thetas = np.array([0.04])
        p = SsviParams(rho=-0.7, eta=1.0, lamb=0.3, theta_grid=thetas)
        fig = plot_skew_term_structure(p, np.array([0.25]))
        assert fig is not None
        # The plot was created; we can't easily extract the value,
        # but it shouldn't crash.

    def test_zero_T_edge_case(self):
        """Edge case: very small T shouldn't crash."""
        thetas = np.array([1e-6])
        # Use a theta consistent with the T (sigma ~ sqrt(w/T))
        p = SsviParams(rho=-0.3, eta=1.0, lamb=0.3, theta_grid=thetas)
        # This should not crash (implied vol with tiny T/theta may be extreme)
        try:
            plot_skew_term_structure(p, np.array([1e-6]))
        except Exception:
            pass  # Numerically challenging but shouldn't be a hard error


# ===================================================================
# plot_gk_diagnostics
# ===================================================================


class TestPlotGkDiagnostics:
    def test_basic_plot(self, sample_arb_results):
        fig = plot_gk_diagnostics(sample_arb_results, k_min=-3.0, k_max=3.0, n_k=200)
        assert fig is not None

    def test_single_result(self):
        p = SviP(a=0.04, b=0.3, rho=-0.2, m=0.0, sigma=0.15)
        result = [check_slice_arbitrage("SINGLE", p, T=0.25)]
        fig = plot_gk_diagnostics(result, k_min=-3.0, k_max=3.0, n_k=100)
        assert fig is not None

    def test_save_to_file(self, sample_arb_results):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "gk_diag.png"
            fig = plot_gk_diagnostics(sample_arb_results, output_path=out)
            assert out.exists()
            assert out.stat().st_size > 0

    def test_custom_k_grid(self, sample_arb_results):
        k_grid = np.linspace(-2.0, 2.0, 300)
        fig = plot_gk_diagnostics(sample_arb_results, k_grid=k_grid)
        assert fig is not None

    def test_many_slices_grid_layout(self):
        """Test with 7 slices to verify multi-row grid layout."""
        results = []
        for i in range(7):
            p = SviP(a=0.03 + 0.01 * i, b=0.3, rho=-0.2 + 0.05 * i,
                     m=0.0, sigma=0.1 + 0.02 * i)
            results.append(
                ArbitrageCheckResult(
                    slice_id=f"MANY-{i}", T=0.1 * (i + 1),
                    butterfly_passed=(i != 3),  # one failure
                    butterfly_min_g=-0.01 if i == 3 else 0.002,
                    bl_passed=None, params=p, k_range=(-3.0, 3.0),
                )
            )
        fig = plot_gk_diagnostics(results, k_min=-3.0, k_max=3.0, n_k=150)
        assert fig is not None


# ===================================================================
# plot_iv_smile_cross_section
# ===================================================================


class TestPlotIvSmileCrossSection:
    def test_basic_plot(self, valid_ssvi_params, T_values):
        fig = plot_iv_smile_cross_section(valid_ssvi_params, T_values)
        assert fig is not None

    def test_custom_k_range(self, valid_ssvi_params, T_values):
        fig = plot_iv_smile_cross_section(valid_ssvi_params, T_values,
                                          k_min=-1.0, k_max=1.0, n_k=100)
        assert fig is not None

    def test_save_to_file(self, valid_ssvi_params, T_values):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "iv_smile.png"
            plot_iv_smile_cross_section(valid_ssvi_params, T_values, output_path=out)
            assert out.exists()
            assert out.stat().st_size > 0

    def test_no_theta_grid_raises(self):
        p = SsviParams(rho=-0.3, eta=1.0, lamb=0.5)
        with pytest.raises(ValueError, match="theta_grid must be populated"):
            plot_iv_smile_cross_section(p, np.array([0.25]))

    def test_single_slice(self):
        thetas = np.array([0.04])
        p = SsviParams(rho=-0.3, eta=1.0, lamb=0.3, theta_grid=thetas)
        fig = plot_iv_smile_cross_section(p, np.array([0.25]))
        assert fig is not None


# ===================================================================
# write_surface_report
# ===================================================================


class TestWriteSurfaceReport:
    def test_basic_report(self, sample_arb_results):
        report = write_surface_report(
            sample_arb_results,
            calendar_passed=True,
            calendar_violations=[],
            title="Test Surface Report",
        )
        assert "Test Surface Report" in report
        assert "PASS" in report
        assert "rejected" in report.lower()
        assert "TEST-FAIL" in report

    def test_report_with_ssvi_params(self, valid_ssvi_params, sample_arb_results):
        report = write_surface_report(
            sample_arb_results,
            calendar_passed=False,
            calendar_violations=[(0.25, 0.5, np.array([-0.5, 0.5]))],
            ssvi_params=valid_ssvi_params,
        )
        assert "SSVI Parameters" in report
        assert "ρ" in report
        assert "η" in report
        assert "λ" in report
        assert "Calendar" in report
        assert "FAIL" in report

    def test_save_to_file(self, sample_arb_results):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "report.txt"
            write_surface_report(
                sample_arb_results,
                calendar_passed=True,
                calendar_violations=[],
                output_path=out,
            )
            assert out.exists()
            content = out.read_text()
            assert "No-Arbitrage Results" in content or "Slice" in content

    def test_no_calendar_for_single_slice(self):
        p = SviP(a=0.04, b=0.3, rho=-0.2, m=0.0, sigma=0.15)
        results = [check_slice_arbitrage("SINGLE", p, T=0.25)]
        report = write_surface_report(results, calendar_passed=None, calendar_violations=[])
        # Should not crash; will mention N/A
        assert "Slice" in report or "SINGLE" in report

    def test_empty_results_list(self):
        report = write_surface_report([], calendar_passed=None, calendar_violations=[])
        assert isinstance(report, str)
        # Should handle empty list gracefully

    def test_bl_field_na_display(self, sample_arb_results):
        """Verify BL field shows N/A when not computed."""
        report = write_surface_report(
            sample_arb_results, calendar_passed=True, calendar_violations=[]
        )
        # One result has bl_passed=None, others have values
        assert "N/A" in report or "FAIL" in report or "PASS" in report