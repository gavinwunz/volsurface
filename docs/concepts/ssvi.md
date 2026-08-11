# SSVI Surface (Surface SVI)

## Definition

The **Surface SVI** parameterization (Gatheral & Jacquier 2014) extends raw SVI
to a full volatility surface across multiple maturities by linking individual
slices through shared global parameters.

For a maturity slice with ATM total variance $`\theta_t`$ and a curvature function
$`\varphi(\theta)`$:

```math
w(k, \theta) = \frac{\theta}{2}
\left(1 + \rho\,\varphi(\theta)\,k + \sqrt{(\varphi(\theta)\,k + \rho)^2 + (1 - \rho^2)}\right)
```

where:

| Parameter | Domain | Interpretation |
|-----------|--------|----------------|
| $`\rho`$ | $`-1 < \rho < 1`$ | Global correlation (skew direction) |
| $`\theta_t`$ | $`\theta_t > 0`$ | ATM total variance per maturity |
| $`\varphi(\theta)`$ | $`\varphi > 0`$ | Curvature function |

## Assumptions

- Raw SVI slices have already been calibrated per expiry.
- The same $`\rho`$ parameter governs skew for every maturity slice — this is
  the key structural assumption that ties the surface together.
- $`\theta_t`$ is monotone non-decreasing in $`t`$ (or is repaired to be).
- The curvature function follows a power-law form (see below).

## The power-law curvature function

VolFoundry uses the canonical form:

```math
\varphi(\theta) = \frac{\eta}{\theta^\lambda}
```

with:

| Parameter | Domain | Interpretation |
|-----------|--------|----------------|
| $`\eta`$ | $`\eta > 0`$ | Curvature scale |
| $`\lambda`$ | $`\lambda \in [0, 1]`$ | Maturity decay exponent |

Special cases:
- $`\lambda = 0`$: constant smile curvature across maturities.
- $`\lambda = 1/2`$: diffusive scaling — smile decays as $`1/\sqrt{T}`$.
  This is the theoretically "safe" range for calendar no-arbitrage.
- $`\lambda = 1`$: fast flattening — smile decays as $`1/T`$.

### Wing asymptotics

```math
\lim_{k \to \pm\infty} \partial_k w(k, \theta) = \frac{\theta}{2} \varphi(\theta) (\rho \pm 1)
```

## Analytical no-arbitrage conditions

The SSVI surface is free of static arbitrage when **all** of these hold:

1. **Positivity**: $`\theta_t > 0`$ for all $`t`$.
2. **Calendar monotonicity**: $`\theta_t`$ is non-decreasing in $`t`$.  When
   market data produces non-monotonic $`\theta`$, VolFoundry reports both the raw
   and (potentially isotonically-adjusted) values.
3. **Correlation domain**: $`\rho \in (-1, 1)`$.
4. **Curvature positivity**: $`\varphi(\theta) > 0`$ for all $`\theta`$.
5. **Lee bound**: $`\eta(1 + |\rho|) \leq 2`$ (ensures finite moments).
6. **Calendar-free condition** (for the power-law form): when
   $`\lambda \in [0, 1/2]`$ and $`\eta(1 + |\rho|) \leq 2`$, the surface is
   guaranteed calendar-arbitrage-free across all $`k`$.

## Implementation

VolFoundry implements SSVI in `volfoundry.surface.ssvi`:

- `SsviParams(rho, eta, lamb, theta_grid)` — global parameters dataclass.
- `ssvi_total_variance(k, theta, phi, rho)` — $`w(k, \theta)`$ for one slice.
- `ssvi_implied_vol(k, theta, phi, rho, T)` — $`\sigma_{\text{IV}}(k, T)`$.
- `ssvi_total_variance_surface(k, thetas, eta, lamb, rho)` — full $`w(k, T)`$ matrix.
- `ssvi_to_raw_svi(theta, phi, rho)` — map SSVI slice to equivalent raw SVI params.
- `SsviParams.satisfies_lee_bound()` — Lee condition check.

### Two-stage calibration

In `calibrate_ssvi_surface`:

1. **Extract $`\theta_t`$**: ATM total variance at each expiry from market data
   (interpolated at $`k = 0`$ from the raw SVI fits).
2. **Global calibration**: Optimise $`(\eta, \lambda, \rho)`$ to minimise
   mean squared total variance error across all slices simultaneously.

If $`\rho`$ is fixed by the user, only $`(\eta, \lambda)`$ are optimised.

### Strict mode enforcement

In `validation="strict"` mode, SSVI parameters that violate the Lee bound
or other analytical conditions cause the fit to be **rejected** and an
`ArbitrageViolationError` raised.  This is enforced during/after parameter
search, not merely checked post-hoc.

## Numerical caveats

- **The Lee bound is enforced in the objective**: a hard penalty term pushes
  the optimizer away from $`\eta(1+|\rho|) > 2`$, and results that still
  violate it are marked `success=False`.
- **$`\theta`$ grid spacing**: Sparse expiry data can make interpolation between
  slices less reliable.  VolFoundry uses log-linear interpolation in $`T`$.
- **What is NOT guaranteed**: The SSVI parametrisation is a model.  Numerical
  checks on a finite grid of $`k`$ and $`T`$ do not prove behaviour on the
  entire real line.  The butterfly check on a $`k`$-grid of 501 points proves
  nothing about points between grid nodes or far outside the grid range.
- **$`\lambda`$ outside $`[0, 1/2]`$**: The Gatheral–Jacquier calendar
  sufficiency proof covers $`\lambda \in [0, 1/2]`$.  VolFoundry allows
  $`\lambda \in [0, 1]`$ but calendar monotonicity is then verified numerically
  rather than being analytically guaranteed.

## References

- Gatheral, J. and Jacquier, A. (2014). "Arbitrage-free SVI volatility surfaces."
  *Quantitative Finance*, 14(1), 59–71.
- Guo, G., Jacquier, A., Martini, C., and Neufcourt, L. (2016). "Generalized
  arbitrage-free SVI volatility surfaces." *SIAM Journal on Financial
  Mathematics*, 7(1), 619–641.

## See also

- [SSVI derivation](../derivations/ssvi.md)
- [SVI parameterization](./svi.md)
- [Arbitrage constraints](./arbitrage.md)