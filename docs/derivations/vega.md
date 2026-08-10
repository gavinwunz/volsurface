# Vega: Derivation from Black-Scholes First Principles

## Assumptions

1. The underlying forward price $F_t$ follows a driftless geometric Brownian
   motion under the $T$-forward measure:
   $$dF_t = \sigma F_t \, dW_t$$
   where $\sigma$ is the (constant) implied volatility and $W_t$ is a standard
   Wiener process.

2. The risk-free discount rate $r$ is constant and continuously compounded.
   The discount factor is $D(T) = e^{-rT}$.

3. European exercise. No early exercise premium.

4. No dividends are paid on the underlying (or equivalently, the dividend
   yield is already embedded in the forward price via put-call parity).

5. Trading is continuous and frictionless (no transaction costs, no bid-ask).

## Black-76 Pricing Formula

Under the $T$-forward measure the price of a European call option with strike
$K$ and time-to-expiry $T$ is the discounted expected payoff:

$$C = e^{-rT} \, \mathbb{E}^{\mathbb{Q}^T}\!\left[\max(F_T - K, 0)\right]$$

Since $F_T = F_0 \exp\!\left(-\frac{\sigma^2}{2}T + \sigma\sqrt{T}\,Z\right)$
with $Z \sim \mathcal{N}(0,1)$, we have:

$$C = e^{-rT}\!\left[F_0 N(d_1) - K N(d_2)\right]$$

where
$$d_1 = \frac{\ln(F_0/K) + \frac{\sigma^2}{2}T}{\sigma\sqrt{T}}, \qquad
  d_2 = d_1 - \sigma\sqrt{T}$$

and $N(\cdot)$ is the standard normal cumulative distribution function:
$$N(x) = \int_{-\infty}^{x} \frac{1}{\sqrt{2\pi}} e^{-t^2/2}\,dt$$

## Definition of Vega

Vega $\mathcal{V}$ is the sensitivity of the option price to a change in the
volatility parameter $\sigma$:

$$\mathcal{V} = \frac{\partial C}{\partial \sigma}$$

Vega is always **positive** for standard European calls and puts — higher
volatility increases the option value in both cases.

## Step 1 — Differentiate the price formula

$$\frac{\partial C}{\partial \sigma} =
   e^{-rT}\!\left[F_0 N'(d_1)\frac{\partial d_1}{\partial \sigma}
                - K N'(d_2)\frac{\partial d_2}{\partial \sigma}\right]$$

## Step 2 — Compute $N'(d_1)$ and $N'(d_2)$

The standard normal density is:
$$N'(x) = n(x) = \frac{1}{\sqrt{2\pi}} e^{-x^2/2}$$

A useful identity (derived below in Step 5):
$$F_0 \, n(d_1) = K \, n(d_2)$$

This is the key relationship that simplifies the vega derivation.

## Step 3 — Compute $\frac{\partial d_1}{\partial \sigma}$ and $\frac{\partial d_2}{\partial \sigma}$

First, compute the derivatives of the d-terms:

$$d_1 = \frac{\ln(F_0/K)}{\sigma\sqrt{T}} + \frac{\sigma\sqrt{T}}{2}$$

$$\frac{\partial d_1}{\partial \sigma} =
   -\frac{\ln(F_0/K)}{\sigma^2\sqrt{T}} + \frac{\sqrt{T}}{2}$$

Observe that:
$$d_2 = \frac{\ln(F_0/K)}{\sigma\sqrt{T}} - \frac{\sigma\sqrt{T}}{2}$$

So:
$$\frac{\partial d_1}{\partial \sigma} = -\frac{d_2}{\sigma}$$

Check:
$$-\frac{d_2}{\sigma} =
   -\frac{1}{\sigma}\!\left(\frac{\ln(F_0/K)}{\sigma\sqrt{T}} -
   \frac{\sigma\sqrt{T}}{2}\right) =
   -\frac{\ln(F_0/K)}{\sigma^2\sqrt{T}} + \frac{\sqrt{T}}{2}
   = \frac{\partial d_1}{\partial \sigma} \quad \checkmark$$

And:
$$\frac{\partial d_2}{\partial \sigma} =
   \frac{\partial d_1}{\partial \sigma} - \sqrt{T} =
   -\frac{d_2}{\sigma} - \sqrt{T} = -\frac{d_2 + \sigma\sqrt{T}}{\sigma}
   = -\frac{d_1}{\sigma}$$

## Step 4 — Substitute and simplify

Substituting the derivative expressions and the identity $F_0 n(d_1) = K n(d_2)$:

$$\mathcal{V} = e^{-rT}\!\left[F_0 n(d_1)\!\left(-\frac{d_2}{\sigma}\right)
                            - K n(d_2)\!\left(-\frac{d_1}{\sigma}\right)\right]$$

$$= \frac{e^{-rT}}{\sigma}\!\left[-F_0 n(d_1)d_2 + K n(d_2)d_1\right]$$

Using $F_0 n(d_1) = K n(d_2) = \xi$:

$$= \frac{e^{-rT}}{\sigma}\,\xi\!\left[-d_2 + d_1\right]$$

$$= \frac{e^{-rT}}{\sigma}\,F_0 n(d_1) \,(d_1 - d_2)$$

Since $d_1 - d_2 = \sigma\sqrt{T}$:

$$\boxed{\mathcal{V} = e^{-rT}\,F_0\,\sqrt{T}\,n(d_1)}$$

## Step 5 — Proof of the identity $F_0 n(d_1) = K n(d_2)$

We need to show $F_0 \exp(-d_2^2/2) = K \exp(-d_1^2/2)$.

Take logs:
$$\ln F_0 - \frac{d_2^2}{2} = \ln K - \frac{d_1^2}{2}$$

$$\ln\frac{F_0}{K} = \frac{1}{2}(d_2^2 - d_1^2) = \frac{1}{2}(d_2 - d_1)(d_2 + d_1)$$

Since $d_2 - d_1 = -\sigma\sqrt{T}$ and $d_1 + d_2 = 2d_1 - \sigma\sqrt{T}$:

$$\ln\frac{F_0}{K} = \frac{1}{2}(-\sigma\sqrt{T})(2d_1 - \sigma\sqrt{T})
                    = -\sigma\sqrt{T}d_1 + \frac{\sigma^2 T}{2}$$

Rearranging:
$$\sigma\sqrt{T}d_1 = \ln\frac{F_0}{K} + \frac{\sigma^2 T}{2}$$

$$d_1 = \frac{\ln(F_0/K) + \sigma^2 T / 2}{\sigma\sqrt{T}}$$

which is exactly the definition of $d_1$. $\quad \square$

## Result

The final expression used in the code:

$$\mathcal{V} = e^{-rT}\,F\,\sqrt{T}\,\frac{1}{\sqrt{2\pi}}\,
                \exp\!\left(-\frac{d_1^2}{2}\right)$$

where:
$$d_1 = \frac{\ln(F/K) + \sigma^2 T / 2}{\sigma\sqrt{T}}$$

## Properties

- **Positivity**: $\mathcal{V} > 0$ for all $F, K, T, r > 0$ (since $e^{-x^2/2} > 0$).
- **ATM maximum**: Vega is maximised near the at-the-money-forward point
  ($F \approx K$), where $d_1 \approx \sigma\sqrt{T}/2$ is smallest in
  absolute value, making $n(d_1)$ largest.
- **Wing decay**: As $K \to 0$ or $K \to \infty$, $d_1 \to \pm\infty$ and
  $n(d_1) \to 0$, so vega vanishes in the deep tails. This is why Newton-Raphson
  fails for deep ITM/OTM options and the Brent fallback is needed.
- $\mathcal{V}$ is the same for calls and puts under Black-76 (it depends only
  on $d_1$, not the option type). This follows from put-call parity:
  $\partial P/\partial\sigma = \partial C/\partial\sigma$ since
  $C - P = e^{-rT}(F - K)$ and the RHS is independent of $\sigma$.