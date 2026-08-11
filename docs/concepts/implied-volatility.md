# Implied Volatility

## Definition

**Implied volatility** (IV) is the value of $`\sigma`$ that, when plugged into
the Black-76 pricing formula, reproduces an observed market price.

Given an observed option price $`C_{\text{market}}`$ (call) or
$`P_{\text{market}}`$ (put) with strike $`K`$, forward $`F`$, time to expiry
$`T`$, and risk-free rate $`r`$, the implied volatility $`\sigma_{\text{IV}}`$
satisfies:

```math
C_{\text{market}} = e^{-rT} \left[ F \Phi(d_1) - K \Phi(d_2) \right]
```

where

```math
d_1 = \frac{\ln(F/K) + \sigma_{\text{IV}}^2 T / 2}{\sigma_{\text{IV}} \sqrt{T}},
\qquad
d_2 = d_1 - \sigma_{\text{IV}} \sqrt{T}
```

and $`\Phi`$ is the standard normal CDF.

## Assumptions

- **Black-76 model**: forward-based formulation; no discounting of the strike
  beyond the $`e^{-rT}`$ factor.
- **European exercise**: no early exercise premium.  Deribit options are European,
  so this is appropriate.
- **Continuous compounding** of the risk-free rate.
- **No dividends** on the underlying (the forward subsumes carry).

## Formula

There is no closed-form inverse.  VolFoundry solves for $`\sigma_{\text{IV}}`$
numerically.

## Implementation

VolFoundry uses a two-stage approach in `volfoundry.iv.black_scholes`:

1. **Seed**: Brenner–Subrahmanyam (1988) approximation

   ```math
   \sigma_0 \approx \sqrt{\frac{2\pi}{T}} \cdot \frac{C}{F}
   ```

   for at-the-money options; modified for off-ATM strikes.

2. **Newton–Raphson** on vega.  If $`|\text{vega}|`$ is too small (deep OTM/ITM)
   or the iteration fails to converge, a **Brent bracketing** fallback takes over.

Convergence tolerance: `VOL_TOL = 1e-8` (decimal volatility).

## Numerical caveats

- **Tiny $`T`$**: As $`T \to 0`$, vega → 0 and the root-finding problem becomes
  ill-conditioned.  VolFoundry floors the vega check at `VEGA_FLOOR = 1e-12`.
- **Price outside no-arbitrage bounds**: $`C \notin [\max(0, e^{-rT}(F-K)),\, e^{-rT}F]`$.
  The solver raises `ImpliedVolError` rather than propagating NaN.
- **Deep in-the-money**: Vega is tiny; Brent fallback handles this reliably to
  the requested tolerance.
- **Deep out-of-the-money**: Very small prices → very small vega → Brent fallback.
- **Vectorised interface**: The batch `implied_vol_brent` function handles arrays
  efficiently; individual failures are raised (not masked out silently).
- **Negative/zero prices**: Rejected at the boundary — no silent NaN propagation.

## References

- Black, F. (1976). "The pricing of commodity contracts." *Journal of Financial
  Economics*, 3(1–2), 167–179.
- Brenner, M. and Subrahmanyam, M. G. (1988). "A simple formula to compute the
  implied standard deviation." *Financial Analysts Journal*, 44(5), 80–83.
- Jackel, P. (2015). "Let's be rational." *Wilmott*, 2015(75), 40–53.

## See also

- [Black-76 derivation](../derivations/vega.md)
- [Volatility smile](./volatility-smile.md)
- [SVI parameterization](./svi.md)