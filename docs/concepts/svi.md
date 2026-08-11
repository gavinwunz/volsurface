# SVI Parameterization (Raw SVI)

## Definition

The **Stochastic Volatility Inspired (SVI)** parameterization (Gatheral 2004)
expresses total implied variance as a function of log-forward-moneyness $`k`$:

```math
w(k) = a + b \left[ \rho (k - m) + \sqrt{(k - m)^2 + \sigma^2} \right]
```

where the five parameters are:

| Parameter | Domain | Interpretation |
|-----------|--------|----------------|
| $`a`$ | $`a > 0`$ | Overall variance level (ATM level) |
| $`b`$ | $`b \geq 0`$ | Slope of the wings |
| $`\rho`$ | $`-1 < \rho < 1`$ | Asymmetry: $`\rho < 0`$ = downward skew |
| $`m`$ | $`m \in \mathbb{R}`$ | Horizontal shift of the smile |
| $`\sigma`$ | $`\sigma > 0`$ | Curvature (smoothness) at the minimum |

## Assumptions

- Black-76 implied volatilities are extracted from market mid prices.
- The parameterization describes **total variance** $`w(k)`$; implied volatility
  is recovered as $`\sigma_{\text{IV}}(k) = \sqrt{w(k) / T}`$.
- One set of SVI parameters per expiry slice.

## Formula and derivatives

### First derivative (wing slope)

```math
w'(k) = b \left[ \rho + \frac{k - m}{\sqrt{(k - m)^2 + \sigma^2}} \right]
```

### Second derivative (curvature / butterfly function)

```math
w''(k) = \frac{b \sigma^2}{\left[(k - m)^2 + \sigma^2\right]^{3/2}}
```

### Minimum total variance

```math
\min_k w(k) = a + b \sigma \sqrt{1 - \rho^2}
```

achieved at $`k = m - \rho\sigma / \sqrt{1 - \rho^2}`$ when $`|\rho| < 1`$.

### Wing asymptotics

```math
\lim_{k \to +\infty} w'(k) = b(\rho + 1), \qquad
\lim_{k \to -\infty} w'(k) = b(\rho - 1)
```

### Lee moment formula

```math
b(1 + |\rho|) \leq 2
```

This bounds the wing slopes to ensure the model-implied risk-neutral distribution
has finite second moment.

### Butterfly function $`g(k)`$

```math
g(k) = \left(1 - \frac{k w'(k)}{2 w(k)}\right)^2 - \frac{w'(k)^2}{4}\left(\frac{1}{w(k)} + \frac{1}{4}\right) + \frac{w''(k)}{2}
```

The condition $`g(k) \geq 0`$ for all $`k`$ is necessary for the absence of
butterfly arbitrage.

## Implementation

VolFoundry implements SVI in `volfoundry.svi.parameterization`:

- `SviParams(a, b, rho, m, sigma)` — validated dataclass.
- `svi_total_variance(k, params)` — $`w(k)`$.
- `svi_implied_vol(k, params, T)` — $`\sigma_{\text{IV}}(k)`$.
- `svi_first_derivative(k, params)` — $`w'(k)`$.
- `svi_second_derivative(k, params)` — $`w''(k)`$.
- `svi_min_total_variance(params)` — analytical minimum.
- `clip_params_to_valid(params)` — project onto valid parameter domain.

### Calibration

The Zeliade quasi-explicit method (`calibrate_svi_slice`) splits the problem:

- **Outer**: 2-parameter optimisation over $`(m, \sigma)`$ via L-BFGS-B.
- **Inner**: Constrained linear least squares for $`(a, b, \rho)`$, solved
  analytically at each outer iteration.

Observation weights default to vega-proportional weighting, giving more influence
to near-ATM quotes where IV is most reliable.  Alternative weighting schemes
(inverse bid-ask spread) are available.

Results are returned as `SviCalibrationResult` with RMSE, R², outer convergence
status, per-parameter diagnostics including bound-proximity warnings.

## Numerical caveats

- **Flat smiles** ($`b \approx 0`$): The SVI form degenerates to constant $`w(k)`$.
  These are handled but return $`b \geq 0`$ at the optimization bound.
- **Duplicate strikes** are averaged before calibration.
- **Minimum quotes**: At least 4 quotes per slice are required for meaningful
  5-parameter calibration (configurable via `SurfaceBuilder`).
- **Parameter clipping**: If `clip_params_to_valid` is used, the clipping is
  recorded so it is never silent.
- **Bound proximity**: When a calibrated parameter lands at a constraint boundary
  (e.g. $`\rho \approx \pm 0.999`$), a warning is emitted because the result may
  be physically implausible.

## References

- Gatheral, J. (2004). "A parsimonious arbitrage-free implied volatility
  parameterization with application to the valuation of volatility derivatives."
  *Global Derivatives & Risk Management*, Madrid.
- Gatheral, J. and Jacquier, A. (2014). "Arbitrage-free SVI volatility surfaces."
  *Quantitative Finance*, 14(1), 59–71.
- Zeliade Systems (2009). "Quasi-explicit calibration of Gatheral's SVI model."
  White paper.

## See also

- [SVI derivation](../derivations/svi.md)
- [SSVI surface](./ssvi.md)
- [Arbitrage constraints](./arbitrage.md)