# No-Arbitrage Conditions for Implied Volatility Surfaces

## 1. Butterfly (g(k)) Condition

### 1.1 Derivation from Breeden-Litzenberger

The Breeden-Litzenberger theorem states that the risk-neutral density q(K)
can be extracted from European call prices C(K) as:

\[
q(K) = e^{rT} \frac{\partial^2 C}{\partial K^2}
\]

For no-arbitrage, we require q(K) >= 0 for all K > 0.

### 1.2 Total variance formulation

Express the call price via the Black-Scholes formula using implied
volatility sigma_IV(k, T), where k = log(K/F) is log-moneyness:

\[
C(K, T) = C_{BS}(F, K, \sigma_{IV}(k, T), T, r)
\]

It's convenient to work with total implied variance:

\[
w(k, T) = \sigma_{IV}^2(k, T) \cdot T
\]

The second derivative d^2C/dK^2 can be expressed in terms of w(k) and its
derivatives w' = dw/dk, w'' = d^2w/dk^2.  After a lengthy computation
(see Gatheral 2004, The Volatility Surface, Chapter 1), we obtain:

\[
\frac{\partial^2 C}{\partial K^2} = e^{-rT} \frac{\phi(d_1)}{K^2 \sqrt{w}}
    \cdot g(k)
\]

where d_1 = -k/sqrt(w) + sqrt(w)/2, phi is the standard normal PDF, and:

\[
g(k) = \left(1 - \frac{k w'}{2w}\right)^2
     - \frac{(w')^2}{4}\left(\frac{1}{w} + \frac{1}{4}\right)
     + \frac{w''}{2}
\]

Since all prefactors (e^{-rT}, phi(d_1), K^2 sqrt(w)) are non-negative,
the sign of q(K) is determined entirely by g(k).  Therefore, the no-arbitrage
condition q(K) >= 0 is equivalent to:

\[
g(k) \geq 0 \quad \forall k \in \mathbb{R}
\]

### 1.3 Assumptions

- r >= 0 (positive risk-free rate)
- sigma_IV > 0 (or equivalently w > 0 for all k)
- T > 0
- The Black-Scholes formula correctly prices European options given the
  implied volatility smile.

### 1.4 SVI-specific form

For the raw SVI parameterization:

\[
w(k) = a + b\left[\rho(k-m) + \sqrt{(k-m)^2 + \sigma^2}\right]
\]

the first and second derivatives are:

\[
w'(k) = b\left[\rho + \frac{k-m}{\sqrt{(k-m)^2 + \sigma^2}}\right]
\]

\[
w''(k) = \frac{b\sigma^2}{((k-m)^2 + \sigma^2)^{3/2}}
\]

Note that w''(k) >= 0 always (since b >= 0, sigma^2 > 0).  This convexity
is necessary but not sufficient for g(k) >= 0.

#### Limiting behavior

As |k| -> infinity:

- w(k) ~ a + b(|k| + rho*k) (linear in |k|)
- w'(k) -> b*rho + b*sign(k) = b*(rho +/- 1)
- w''(k) -> 0

Plugging into g(k):

For large |k|, term3 = w''/2 -> 0.  The dominant terms are:

\[
g(k) \sim \left(1 - \frac{k \cdot b(\rho \pm 1)}{2b|k|}\right)^2
      - \frac{b^2(\rho \pm 1)^2}{4b|k|}
\]

where the + sign is for k -> +inf and - sign for k -> -inf.

For the right wing (k -> +inf): g ~ (1 - (rho+1)/2)^2 > 0
For the left wing (k -> -inf):  g ~ (1 + (rho-1)/2)^2 > 0

So g(k) > 0 in the tails provided |rho| < 1 and b > 0, which are
satisfied by construction.  Violations, if any, must occur in the
interior (near ATM).

---

## 2. Calendar Spread Condition

### 2.1 Statement

A necessary condition for no calendar arbitrage is that total implied
variance is non-decreasing in time to expiry at each fixed log-moneyness:

\[
w(k, T_i) \leq w(k, T_j) \quad \text{for all } T_i < T_j \text{ and all } k
\]

### 2.2 Derivation

Consider a calendar spread: long an option with expiry T_j and short an
option with the same strike on the earlier expiry T_i.  The price of this
calendar spread is:

\[
C(K, T_j) - C(K, T_i)
\]

For no arbitrage, this must be >= 0 (it costs money to hold the option).
The Black-Scholes price is a monotonic function of total variance
w(K, T) = sigma_IV^2 * T (for a given forward and strike).  Therefore,
the calendar no-arbitrage condition reduces to:

\[
w(k, T_i) \leq w(k, T_j) \quad \forall k
\]

### 2.3 Assumptions

- Same underlying, same rate r, same forward F at both expiries.
- No dividends or discrete events between T_i and T_j that would cause
  the forward to jump.
- The option with the longer maturity is strictly more valuable because
  time to expiry is a monotonic source of optionality value.

---

## 3. Breeden-Litzenberger Density (Cross-Check)

### 3.1 Finite difference approximation

Given implied volatilities sigma_i at strikes K_i, we first compute
call prices via Black-76:

\[
C_i = e^{-rT}\left[F \Phi(d_1) - K_i \Phi(d_2)\right]
\]

where d_1 = (log(F/K_i) + sigma_i^2 T/2) / (sigma_i sqrt(T)),
d_2 = d_1 - sigma_i sqrt(T).

The second derivative d^2C/dK^2 is approximated via the non-uniform
three-point formula (derived by fitting a quadratic through three
consecutive points):

\[
\frac{d^2C}{dK^2}(K_i) = \frac{2[C_{i+1}h_0 - C_i(h_0 + h_1) + C_{i-1}h_1]}
                            {(h_0 + h_1)h_1h_0}
\]

where h_0 = K_i - K_{i-1}, h_1 = K_{i+1} - K_i.

The risk-neutral density is then:

\[
q(K_i) = e^{rT} \frac{d^2C}{dK^2}(K_i)
\]

### 3.2 Non-negativity check

For no-arbitrage, we require q(K_i) >= 0 for all interior strikes
(excluding endpoints where the finite difference is undefined).

### 3.3 Assumptions

- K_i are monotonically increasing.
- Implied vols are smooth enough that the quadratic approximation is
  valid (sufficiently dense strike grid).
- The non-uniform formula correctly handles varying strike spacing.