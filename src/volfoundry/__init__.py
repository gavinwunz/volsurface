"""VolFoundry -- open-source volatility infrastructure for derivatives.

VolFoundry turns live or historical option chains into calibrated volatility
surfaces with explicit numerical diagnostics and reproducible market snapshots.

.. code-block:: python

    from volfoundry import DeribitClient, SurfaceBuilder

    snapshot = DeribitClient().fetch("BTC")
    result = SurfaceBuilder().fit(snapshot, validation="strict")
    print(result.surface.iv(strike=70000, maturity=30 / 365.25))
    print(result.validation.is_valid)
"""

__version__ = "0.0.1"

# After the P3 milestone, this module will export a curated public API.
# For now, the internal subpackage modules remain directly importable.
__all__: list[str] = ["__version__"]