# SSVI (Surface SVI) Parameterization — Full Derivation

## Reference

Gatheral, J. and Jacquier, A. (2014). "Arbitrage-free SVI volatility surfaces."
Quantitative Finance, 14(1), 59–71.

---

## 1. Motivation

Raw SVI calibrates each maturity slice independently, producing $n$ sets of
parameters $\{a_t, b_t, \rho_t, m_t, \sigma_t\}$ for $n$ expiries. This means:

- The correlation $\rho_t$ (skew) can vary freely across maturities, often
  producing an inconsistent term structure.
- There is no guarantee that the $\{w(k, T_t)\}$ surface is calendar-arbitrage-free:
  $w(k, T)$ may not be monotonic in $T$ at fixed $k$.
- The parameterisation has 5 parameters per slice; with 10 expiries that is
  50 independent degrees of freedom, prone to overfitting.

The SSVI (Surface SVI) parameterisation addresses these issues by imposing a
global structure:

1. A **single** correlation $\rho$ across all maturities.
2. ATM total variance $\theta_t = w(0, T_t)$ extracted from the market.
3. A curvature function $\phi(\theta_t)$ that controls how the smile shape
   evolves with maturity, typically a power law $\phi(\theta) = \eta / \theta^\lambda$.

This reduces the surface to just $n_T + 3$ parameters: $\{\theta_t\}_{t=1}^{n_T}$,
$\rho$, $\eta$, and $\lambda$.

---

## 2. SSVI Functional Form

### 2.1 Definition

The SSVI total implied variance is:

$$w(k, \theta) = \frac{\theta}{2}\left(1 + \rho\,\phi(\theta)\,k + \sqrt{\big(\phi(\theta)\,k + \rho\big)^2 + (1 - \rho^2)}\right)$$

where:
- $k = \log(K/F)$ is log-forward-moneyness.
- $\theta = \sigma_{\text{ATM}}^2 T$ is the ATM total variance.
- $\rho \in (-1, 1)$ is the global correlation.
- $\phi(\theta) > 0$ is the curvature function.

### 2.2 ATM Value

At $k = 0$:

$$\begin{aligned}
w(0, \theta) &= \frac{\theta}{2}\left(1 + 0 + \sqrt{\rho^2 + (1 - \rho^2)}\right) \\[4pt]
&= \frac{\theta}{2}\left(1 + \sqrt{1}\right) \\[4pt]
&= \frac{\theta}{2} \cdot 2 = \theta
\end{aligned}$$

So $w(0, \theta) = \theta$ as required — the ATM total variance is exactly $\theta$.

### 2.3 Wing Asymptotics

For large $|k|$:

$$\begin{aligned}
\sqrt{(\phi k + \rho)^2 + (1 - \rho^2)} &= |\phi k + \rho| \sqrt{1 + \frac{1 - \rho^2}{(\phi k + \rho)^2}} \\[4pt]
&\approx |\phi k + \rho| \left(1 + \frac{1 - \rho^2}{2(\phi k + \rho)^2}\right) \\[4pt]
&\approx |\phi k + \rho|
\end{aligned}$$

For $k \to +\infty$ (call wing), $\phi k + \rho > 0$, so:

$$\begin{aligned}
w(k, \theta) &\approx \frac{\theta}{2}\left(1 + \rho\phi k + \phi k + \rho\right) \\[4pt]
&= \frac{\theta}{2}\left((1 + \rho) + \phi(1 + \rho)k\right)
\end{aligned}$$

The asymptotic slope is $\frac{\theta\phi(1 + \rho)}{2}$, which gives a right-wing
total variance slope of:

$$w'(+\infty) = \frac{\theta\phi(1 + \rho)}{2}$$

For $k \to -\infty$ (put wing), $\phi k + \rho < 0$, so:

$$\begin{aligned}
w(k, \theta) &\approx \frac{\theta}{2}\left(1 + \rho\phi k - \phi k - \rho\right) \\[4pt]
&= \frac{\theta}{2}\left((1 - \rho) + \phi(\rho - 1)k\right)
\end{aligned}$$

The asymptotic slope is $\frac{\theta\phi(\rho - 1)}{2}$, giving:

$$w'(-\infty) = \frac{\theta\phi(\rho - 1)}{2}$$

### 2.4 Lee's Moment Formula Constraint

Lee (2004) proved that for any arbitrage-free implied volatility surface, the
asymptotic slope of the total implied variance satisfies $|w'(k)| \leq 2$ as
$k \to \pm\infty$. For SSVI this gives:

$$\frac{\theta\phi(1 + |\rho|)}{2} \leq 2$$

Since $\phi(\theta) = \eta / \theta^\lambda$ with $\lambda \geq 0$, the
maximum of $\theta\,\phi(\theta) = \eta\,\theta^{1-\lambda}$ over $\theta$
occurs at $\theta = 1$ (for $\lambda < 1$) or is bounded by $\eta$ (for
$\lambda = 1$, since $\theta^{0} = 1$). In all cases the worst-case bound is:

$$\boxed{\eta\,(1 + |\rho|) \leq 2}$$

This is the Lee moment formula constraint for SSVI.

---

## 3. Curvature Function: Power Law

### 3.1 Definition

$$\phi(\theta) = \frac{\eta}{\theta^\lambda}, \quad \eta > 0,\ \lambda \in [0, 1]$$

**Assumptions**:
- $\eta > 0$ ensures positive curvature (no flat surface at the ATM).
- $\lambda \in [0, 1]$ is the extended range from Gatheral & Jacquier.

### 3.2 Interpretation of $\lambda$

- **$\lambda = 0$**: $\phi(\theta) = \eta$, constant curvature across all
  maturities. The smile does not flatten with time. This violates the central
  limit intuition that returns approach normality over long horizons, but is
  sometimes observed in short-dated commodity options.
- **$\lambda = 1/2$**: $\phi(\theta) = \eta / \sqrt{\theta}$, diffusive scaling.
  Since $\theta = \sigma_{\text{ATM}}^2 T$, we get $\phi \propto 1/\sqrt{T}$.
  The smile decays as $1/\sqrt{T}$, consistent with the central limit theorem.
- **$\lambda = 1$**: $\phi(\theta) = \eta / \theta$, fast flattening.
  The smile decays as $1/T$.

### 3.3 Calendar No-Arbitrage ($\lambda \leq 1/2$)

Gatheral & Jacquier (2014) proved that the condition:

$$\frac{\partial w(k, \theta)}{\partial \theta} \geq 0 \quad \forall k$$

(calendar arbitrage-free) is **automatically satisfied** when $\lambda \in [0, 1/2]$
and $\eta(1 + |\rho|) \leq 2$.

For $\lambda \in (1/2, 1]$, calendar arbitrage must be checked explicitly on a
case-by-case basis.

---

## 4. Explicit First Derivative

Differentiate $w(k, \theta)$ with respect to $k$:

Let $u = \phi k + \rho$ and $D = \sqrt{u^2 + (1 - \rho^2)}$.

$$w(k, \theta) = \frac{\theta}{2}\left(1 + \rho\phi k + D\right)$$

Then:

$$\begin{aligned}
\frac{\partial D}{\partial k} &= \frac{\partial}{\partial k}\sqrt{u^2 + (1 - \rho^2)} \\[4pt]
&= \frac{u \cdot u'}{\sqrt{u^2 + (1 - \rho^2)}} \\[4pt]
&= \frac{(\phi k + \rho)\,\phi}{D}
\end{aligned}$$

So:

$$\begin{aligned}
w'(k, \theta) &= \frac{\theta}{2}\left(\rho\phi + \frac{(\phi k + \rho)\,\phi}{D}\right) \\[4pt]
&= \frac{\theta\phi}{2}\left(\rho + \frac{\phi k + \rho}{D}\right)
\end{aligned}$$

At $k = 0$, $D = \sqrt{\rho^2 + (1 - \rho^2)} = 1$, so:

$$w'(0, \theta) = \frac{\theta\phi}{2}(\rho + \rho) = \theta\,\rho\,\phi$$

This gives the ATM skew directly: negative $\rho$ gives negative ATM skew
(put wing higher, as in equity markets).

---

## 5. Equivalence to Raw SVI

The SSVI form is a special case of raw SVI:

$$w_{\text{SVI}}(k) = a + b\left[\rho_{\text{SVI}}(k - m) + \sqrt{(k - m)^2 + \sigma^2}\right]$$

with the mapping:

$$\boxed{
\begin{aligned}
a &= \frac{\theta}{2}(1 - \rho^2) \\[4pt]
b &= \frac{\theta\phi}{2} \\[4pt]
\rho_{\text{SVI}} &= \rho \\[4pt]
m &= -\frac{\rho}{\phi} \\[4pt]
\sigma^2 &= \frac{1 - \rho^2}{\phi^2}
\end{aligned}}
$$

**Derivation**: Expand the SSVI form and match coefficients.

$$\begin{aligned}
w_{\text{SSVI}}(k) &= \frac{\theta}{2}\left(1 + \rho\phi k + \sqrt{(\phi k + \rho)^2 + (1 - \rho^2)}\right) \\[4pt]
&= \frac{\theta}{2} + \frac{\theta\rho\phi}{2}k + \frac{\theta}{2}\sqrt{(\phi k + \rho)^2 + (1 - \rho^2)}
\end{aligned}$$

Now:

$$\begin{aligned}
(\phi k + \rho)^2 + (1 - \rho^2) &= \phi^2k^2 + 2\rho\phi k + \rho^2 + 1 - \rho^2 \\[4pt]
&= \phi^2 k^2 + 2\rho\phi k + 1
\end{aligned}$$

Factor $\phi^2$:

$$= \phi^2\left(k^2 + \frac{2\rho}{\phi}k + \frac{1}{\phi^2}\right)$$

Complete the square:

$$\begin{aligned}
k^2 + \frac{2\rho}{\phi}k + \frac{1}{\phi^2} &= \left(k + \frac{\rho}{\phi}\right)^2 - \frac{\rho^2}{\phi^2} + \frac{1}{\phi^2} \\[4pt]
&= \left(k + \frac{\rho}{\phi}\right)^2 + \frac{1 - \rho^2}{\phi^2}
\end{aligned}$$

So:

$$\sqrt{(\phi k + \rho)^2 + (1 - \rho^2)} = \phi\sqrt{\left(k + \frac{\rho}{\phi}\right)^2 + \frac{1 - \rho^2}{\phi^2}}$$

Substituting back:

$$\begin{aligned}
w_{\text{SSVI}}(k) &= \frac{\theta}{2} + \frac{\theta\rho\phi}{2}k + \frac{\theta\phi}{2}\sqrt{\left(k + \frac{\rho}{\phi}\right)^2 + \frac{1 - \rho^2}{\phi^2}} \\[4pt]
&= \frac{\theta}{2} + \frac{\theta\phi}{2}\left[\rho k + \sqrt{(k - m)^2 + \sigma^2}\right]
\end{aligned}$$

where $m = -\rho/\phi$ and $\sigma^2 = (1 - \rho^2)/\phi^2$.

Now rewrite to match $a + b[\rho(k - m) + \sqrt{(k-m)^2 + \sigma^2}]$:

$$\begin{aligned}
&= \frac{\theta}{2} + \frac{\theta\phi}{2}\left[\rho(k - m + m) + \sqrt{(k-m)^2 + \sigma^2}\right] \\[4pt]
&= \frac{\theta}{2} + \frac{\theta\phi}{2}\left[\rho(k - m) - \frac{\rho^2}{\phi} + \sqrt{(k-m)^2 + \sigma^2}\right] \\[4pt]
&= \frac{\theta}{2} - \frac{\theta\rho^2}{2} + \frac{\theta\phi}{2}\left[\rho(k - m) + \sqrt{(k-m)^2 + \sigma^2}\right] \\[4pt]
&= \frac{\theta(1 - \rho^2)}{2} + \frac{\theta\phi}{2}\left[\rho(k - m) + \sqrt{(k-m)^2 + \sigma^2}\right]
\end{aligned}$$

Hence $a = \frac{\theta}{2}(1 - \rho^2)$ and $b = \frac{\theta\phi}{2}$. QED.

---

## 6. No-Arbitrage Conditions Summary

| Condition | Formula | SSVI Guarantee |
|---|---|---|
| **Positive variance** | $w(k) \geq 0$ | $a > 0$ (since $\theta > 0, |\rho| < 1$) |
| **Butterfly** | $g(k) \geq 0$ | Must verify numerically |
| **Calendar (calib.-free)** | $\partial_\theta w(k, \theta) \geq 0$ | Automatic when $\lambda \in [0, 1/2]$ and $\eta(1+|\rho|) \leq 2$ |
| **Calendar (general)** | $\partial_T w(k, T) \geq 0$ | Must verify if $\lambda > 1/2$ |
| **Lee bound** | $|w'(\pm\infty)| \leq 2$ | $\eta(1+|\rho|) \leq 2$ |

### 6.1 Why Calendar is Calibration-Free for $\lambda \leq 1/2$

Gatheral & Jacquier (2014, Theorem 4.2) proved that when $\phi(\theta) = \eta / \theta^\lambda$
with $\lambda \in [0, 1/2]$, the function:

$$f_\theta(k) = \frac{\partial w(k, \theta)}{\partial \theta}$$

is exactly zero at $k = -\rho/\phi$ and non-negative everywhere else, provided
$\eta(1 + |\rho|) \leq 2$. In our implementation, when $\lambda > 1/2$ we
check calendar monotonicity by evaluating $w(k, \theta)$ on a grid and
verifying it is non-decreasing in $\theta$ at every $k$.

---

## 7. Implementation Notes

1. **ATM extraction**: $\theta_t$ is extracted from market data at each expiry
   by interpolating $w_{\text{obs}}(k)$ at $k = 0$. The SSVI calibration does
   NOT fit $\theta_t$ — it uses market-observed ATM variances directly.

2. **Calibration**: With $\theta_t$ fixed, the remaining parameters $(\rho, \eta, \lambda)$
   are calibrated via least-squares minimisation:

   $$\min_{\rho, \eta, \lambda} \sum_{t} \sum_i \omega_{t,i}\left(w_{\text{obs}}(k_i, T_t) - w_{\text{SSVI}}(k_i, \theta_t; \rho, \eta, \lambda)\right)^2$$

   subject to $|\rho| < 1$, $\eta > 0$, $\lambda \in [0, 1]$, and
   $\eta(1 + |\rho|) \leq 2$.

3. **Two-stage strategy**: The implementation supports fixing $\rho$ (from a
   preliminary raw SVI calibration) and fitting only $(\eta, \lambda)$, or
   fitting all three jointly. The two-stage approach is more robust in practice.

4. **Fallback**: When the optimiser fails or calendar violations are detected,
   the fit is reported as-is with violations logged — never silently accepted.