# The Volatility Smile

## Definition

The **volatility smile** (or skew) is the observation that options with different
strikes trade at different implied volatilities, even when they share the same
underlying and expiry.  In a Black–Scholes world with known, constant volatility,
every option on the same underlying would have the same IV.  The fact that they
don't tells us the market prices in non-lognormal return distributions and
stochastic volatility.

## Assumptions

- Implied volatility is extracted from mid-market option prices using Black-76.
- The underlying forward $`F`$ is estimated from put-call parity.
- The smile is parameterised in terms of **log-forward-moneyness**

  ```math
  k = \log(K / F)
  ```

  where $`K`$ is the strike and $`F`$ is the forward price.

## The shape

**Equity and crypto markets** typically show a **negative skew** (downward slope):
OTM puts (low strikes, $`k < 0`$) carry higher IV than OTM calls ($`k > 0`$).
This reflects the "crash premium" — the market prices in greater downside risk.

**FX markets** often show a symmetric smile (high IV at both wings), reflecting
symmetric tail risk.

**Commodities** can show positive skew depending on supply/demand dynamics.

A typical BTC smile on Deribit as of mid-2026:

```text
     k     | -2.0  -1.0   0.0   1.0   2.0
σ_IV(decimal)| 0.85  0.70  0.55  0.42  0.35
```

## Total variance scale

Rather than working directly with implied volatility, the SVI/SSVI framework
works with **total implied variance**:

```math
w(k, T) = \sigma_{\text{IV}}^2(k, T) \cdot T
```

This has the advantage that calendar arbitrage constraints ($`\partial_T w \geq 0`$)
are linear in $`w`$ and easier to enforce.

## Parameterization vs interpolation

VolFoundry does **not** interpolate raw market IVs.  Instead, it fits a
parametric model (SVI per slice, SSVI across slices) that:

1. Smooths market microstructure noise.
2. Provides a functional form with known analytical derivatives.
3. Allows enforcement of no-arbitrage constraints directly on the parameters.

## Numerical caveats

- The fitted smile is a model — it won't hit every market mid exactly.  The
  per-slice RMSE (typically 0.2–3 vol points) gives the fit quality.
- Wing extrapolation (far from market strikes) is model-driven.  The SVI wing
  asymptotics ($`w(k) \sim b(\rho \pm 1)|k|`$ as $`k \to \pm\infty`$) may not
  reflect the true market tail.
- Lee's moment formula bounds $`b(1 + |\rho|) \leq 2`$ ensure the model-implied
  distribution has finite moments.

## References

- Gatheral, J. (2006). *The Volatility Surface: A Practitioner's Guide*. Wiley.
- Derman, E. and Miller, M. B. (2016). *The Volatility Smile*. Wiley.

## See also

- [SVI parameterization](./svi.md)
- [SSVI surface](./ssvi.md)
- [Arbitrage constraints](./arbitrage.md)