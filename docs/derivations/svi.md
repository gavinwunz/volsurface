# Raw SVI Parameterization: Derivation and Properties

## Assumptions

1. The implied volatility surface is parameterized in terms of total implied
   variance $w(k) = \sigma_{\text{IV}}^2(k) \cdot T$, where $k = \log(K/F)$
   is log-forward-moneyness.

2. The SVI (Stochastic Volatility Inspired) parameterization, introduced by
   Gatheral (2004), is a parsimonious functional form that captures the
   observed smile/skew patterns while satisfying asymptotic no-arbitrage
   constraints.

3. We work under the risk-neutral measure. The discount factor is
   $D(T) = e^{-rT}$ with constant risk-free rate $r$.

4. We assume European exercise on a single expiry slice. Each maturity is
   calibrated independently (raw SVI); cross-maturity consistency is enforced
   later via SSVI (M6).

## The Raw SVI Functional Form

The raw SVI expresses total implied variance as:

$$w(k) = a + b\left[\rho(k - m) + \sqrt{(k - m)^2 + \sigma^2}\right]$$

with five parameters:

| Parameter | Domain        | Interpretation                                     |
|-----------|---------------|----------------------------------------------------|
| $a$       | $a > 0$       | Overall variance level (vertical shift)            |
| $b$       | $b \geq 0$    | Slope of the wings (controls smile convexity)      |
| $\rho$    | $-1 < \rho < 1$| Asymmetry (negative = equity-like skew)           |
| $m$       | $\mathbb{R}$  | Horizontal translation (shifts the smile)          |
| $\sigma$  | $\sigma > 0$  | Curvature / smoothness at the ATM point            |

## First Derivative and Wing Slopes

The first derivative with respect to log-moneyness is:

$$\begin{aligned}
w'(k) &= \frac{d}{dk}\left[a + b\left(\rho(k-m) + \sqrt{(k-m)^2 + \sigma^2}\right)\right] \\[4pt]
      &= b\left[\rho + \frac{k-m}{\sqrt{(k-m)^2 + \sigma^2}}\right]
\end{aligned}$$

For the asymptotic wings, we take the limits:

**Right wing** ($k \to +\infty$):
$$\lim_{k \to +\infty} w'(k) = b\left(\rho + 1\right)$$

**Left wing** ($k \to -\infty$):
$$\lim_{k \to -\infty} w'(k) = b\left(\rho - 1\right)$$

### Lee's Moment Formula and the Slope Bound of 2

Roger Lee (2004) proved that for any arbitrage-free implied volatility surface,
the asymptotic slope of total implied variance is bounded:

$$\left|\lim_{k \to \pm\infty} \frac{\partial w}{\partial k}\right| \leq 2$$

This follows from the finiteness of the moment-generating function of the
underlying. For SVI, Lee's bound translates to:

$$b(1 + |\rho|) \leq 2$$

**Proof sketch (Lee 2004):** Let $q^* = \sup\{q : \mathbb{E}[S_T^{1+q}] < \infty\}$
be the maximal finite moment of the spot. Then the right-wing implied variance
slope satisfies:

$$\limsup_{k \to \infty} \frac{w(k)}{|k|} = \beta_R \quad\text{with}\quad \beta_R = g(q^*)$$

where $g(x) = 2 - 4(\sqrt{x^2 + x} - x)$. The function $g$ is bounded by 2,
attained only when all moments exist ($q^* = \infty$). Since |slope| = |w'|
is the asymptotic growth rate of $w$, we have $|w'(\pm\infty)| \leq 2$.

For the SVI parameterization, this imposes:
$$b(\rho + 1) \leq 2 \quad\text{and}\quad -b(\rho - 1) \leq 2$$
which combine to $b(1 + |\rho|) \leq 2$.

## Second Derivative and Curvature

The second derivative is:

$$\begin{aligned}
w''(k) &= \frac{d}{dk}\left[b\left(\rho + \frac{k-m}{\sqrt{(k-m)^2 + \sigma^2}}\right)\right] \\[4pt]
       &= b \cdot \frac{\sqrt{(k-m)^2 + \sigma^2} - (k-m) \cdot \frac{k-m}{\sqrt{(k-m)^2 + \sigma^2}}}{(k-m)^2 + \sigma^2} \\[4pt]
       &= b \cdot \frac{(k-m)^2 + \sigma^2 - (k-m)^2}{((k-m)^2 + \sigma^2)^{3/2}} \\[4pt]
       &= \frac{b\,\sigma^2}{((k-m)^2 + \sigma^2)^{3/2}}
\end{aligned}$$

Since $b \geq 0$ and $\sigma > 0$, we have $w''(k) \geq 0$ for all $k$. This
is a necessary condition for no-arbitrage (convexity of total variance is
required for the Breeden-Litzenberger density to be non-negative). However,
$w''(k) \geq 0$ is a consequence of the SVI form *only when $b \geq 0$*;
the butterfly condition (M4) provides the full check.

The maximum curvature occurs at $k = m$, with value:
$$w''(m) = \frac{b}{\sigma}$$

This shows the trade-off: larger $\sigma$ smooths the smile (lower peak
curvature), while larger $b$ steepens it.

## Minimum Total Variance

Setting $w'(k) = 0$ to find the minimum:

$$\begin{aligned}
b\left[\rho + \frac{k-m}{\sqrt{(k-m)^2 + \sigma^2}}\right] &= 0 \\[4pt]
\frac{k-m}{\sqrt{(k-m)^2 + \sigma^2}} &= -\rho
\end{aligned}$$

Squaring both sides (noting that sign($k-m$) = -sign($\rho$)):

$$(k-m)^2 = \rho^2\left((k-m)^2 + \sigma^2\right)$$
$$(k-m)^2(1 - \rho^2) = \rho^2\sigma^2$$
$$|k-m| = \frac{|\rho|\,\sigma}{\sqrt{1 - \rho^2}}$$

The minimizer is:
$$k^* = m - \frac{\rho\sigma}{\sqrt{1 - \rho^2}}$$

The minimum total variance is:

$$\begin{aligned}
w(k^*) &= a + b\left[\rho\left(-\frac{\rho\sigma}{\sqrt{1-\rho^2}}\right) + \sqrt{\frac{\rho^2\sigma^2}{1-\rho^2} + \sigma^2}\right] \\[4pt]
       &= a + b\left[-\frac{\rho^2\sigma}{\sqrt{1-\rho^2}} + \frac{\sigma}{\sqrt{1-\rho^2}}\right] \\[4pt]
       &= a + \frac{b\sigma(1 - \rho^2)}{\sqrt{1 - \rho^2}} \\[4pt]
       &= a + b\,\sigma\sqrt{1 - \rho^2}
\end{aligned}$$

Since $b \geq 0$, $\sigma > 0$, and $|\rho| < 1$, we have
$b\sigma\sqrt{1-\rho^2} \geq 0$, so with $a > 0$, the minimum total variance
is always positive: $w(k^*) > 0$.

## Vega Weights (Motivation)

When calibrating SVI to market data, the residuals $\|w_{\text{obs}}(k_i) - w(k_i)\|$
should be weighted by the sensitivity of the option price to volatility:

$$\text{vega} = \frac{\partial C}{\partial \sigma} = F\,e^{-rT}\,N'(d_1)\sqrt{T}$$

where $d_1 = \frac{\log(F/K) + \sigma^2 T/2}{\sigma\sqrt{T}}$ and $N'(\cdot)$
is the standard normal density. Vega is highest near the ATM point and decays
in the wings, so vega weighting ensures the fit prioritizes the region where
options are most sensitive to volatility misspecification.

## References

- Gatheral, J. (2004). "A parsimonious arbitrage-free implied volatility
  parameterization with application to the valuation of volatility derivatives."
  Presentation at Global Derivatives.
- Gatheral, J. and Jacquier, A. (2014). "Arbitrage-free SVI volatility surfaces."
  *Quantitative Finance*, 14(1), 59–71.
- Lee, R. (2004). "The moment formula for implied volatility at extreme strikes."
  *Mathematical Finance*, 14(3), 469–480.
- Zeliade Systems (2011). "Quasi-explicit calibration of Gatheral's SVI model."
  Zeliade white paper.