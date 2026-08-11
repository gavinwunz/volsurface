"""Cox-Ross-Rubinstein (CRR) binomial tree pricer.

Pricing
-------
The CRR tree models the underlying forward price F evolving multiplicatively:

    u = exp(sigma * sqrt(dt))          (up factor)
    d = 1 / u                          (down factor)
    p = (exp((r - q)*dt) - d) / (u - d)   (risk-neutral up probability)

Since we work in Black-76 space (forwards), the forward F grows at rate (r - q).
For the standard Black-76 case where F already embeds the carry, we use:

    p = (1 - d) / (u - d)   when using forward as numéraire (r-q = 0 in forward measure).

After constructing the tree out to N steps, the option value is computed by
backwards induction:

    - European:  V_i = exp(-r*dt) * [p*V_{i+1}^{up} + (1-p)*V_{i+1}^{down}]
    - American:  V_i = max(intrinsic, continuation)

where intrinsic for calls is F_i - K and for puts is K - F_i.

Greeks
------
Delta, Gamma, Theta are computed via finite differences on the tree:

    Delta  = (V(1,1) - V(1,0)) / (F*u - F*d)
    Gamma  = ((V(2,2)-V(2,1))/(F*u^2-F) - (V(2,1)-V(2,0))/(F-F*d^2))
             / (0.5*(F*u^2 - F*d^2))
    Theta  = (V(2,1) - V(0,0)) / (2*dt)

where V(i,j) is the option value at time step i and node j (j up-moves).

References
----------
Cox, J. C., Ross, S. A., & Rubinstein, M. (1979). "Option pricing: A simplified
approach." Journal of Financial Economics, 7(3), 229-263.
"""

from __future__ import annotations

import math

from volfoundry.iv.black_scholes import OptionType


def crr_price(
    F: float,
    K: float,
    sigma: float,
    T: float,
    r: float,
    N: int = 300,
    option_type: OptionType = OptionType.CALL,
    american: bool = False,
) -> float:
    """Price a European or American option using the CRR binomial tree.

    Parameters
    ----------
    F : float
        Forward price of the underlying.
    K : float
        Strike price.
    sigma : float
        Volatility (decimal).
    T : float
        Time to expiry in years.
    r : float
        Risk-free / discount rate (continuous).
    N : int
        Number of time steps (default 300).
    option_type : OptionType
        CALL or PUT.
    american : bool
        If True, price as American (early exercise); otherwise European.

    Returns
    -------
    float
        Option price.
    """
    if N < 1:
        raise ValueError("N must be >= 1")

    if sigma <= 0 or T <= 0 or F <= 0 or K <= 0:
        df = math.exp(-r * T)
        if option_type == OptionType.CALL:
            return float(df * max(F - K, 0.0))
        else:
            return float(df * max(K - F, 0.0))

    dt = T / N
    u = math.exp(sigma * math.sqrt(dt))
    d = 1.0 / u
    df_step = math.exp(-r * dt)

    # Risk-neutral probability in the forward measure (no drift on F)
    p = (1.0 - d) / (u - d)

    # Clamp to [0, 1] for numerical safety
    p = max(0.0, min(1.0, p))

    # ------------------------------------------------------------------
    # Build terminal payoffs
    # ------------------------------------------------------------------
    # After N steps, there are N+1 distinct nodes: j up-moves, N-j down-moves
    # Terminal forward: F * u^j * d^(N-j)
    values = [0.0] * (N + 1)
    for j in range(N + 1):
        F_terminal = F * (u**j) * (d ** (N - j))
        if option_type == OptionType.CALL:
            values[j] = max(F_terminal - K, 0.0)
        else:
            values[j] = max(K - F_terminal, 0.0)

    # ------------------------------------------------------------------
    # Backward induction
    # ------------------------------------------------------------------
    for i in range(N - 1, -1, -1):
        for j in range(i + 1):
            continuation = df_step * (p * values[j + 1] + (1.0 - p) * values[j])
            if american:
                F_node = F * (u**j) * (d ** (i - j))
                if option_type == OptionType.CALL:
                    intrinsic = max(F_node - K, 0.0)
                else:
                    intrinsic = max(K - F_node, 0.0)
                values[j] = max(intrinsic, continuation)
            else:
                values[j] = continuation

    return float(values[0])


def crr_greeks(
    F: float,
    K: float,
    sigma: float,
    T: float,
    r: float,
    N: int = 300,
    option_type: OptionType = OptionType.CALL,
) -> dict[str, float]:
    """Compute CRR price alongside Delta, Gamma, and Theta via tree FD.

    Uses the first two steps of the tree for finite-difference Greeks.

    Parameters
    ----------
    F, K, sigma, T, r, N, option_type : see crr_price.

    Returns
    -------
    dict
        Keys: price, delta, gamma, theta.
    """
    if N < 3:
        raise ValueError("N must be >= 3 for Greeks computation")

    if sigma <= 0 or T <= 0 or F <= 0 or K <= 0:
        df = math.exp(-r * T)
        if option_type == OptionType.CALL:
            price = float(df * max(F - K, 0.0))
        else:
            price = float(df * max(K - F, 0.0))
        return {"price": price, "delta": 0.0, "gamma": 0.0, "theta": 0.0}

    dt = T / N
    u = math.exp(sigma * math.sqrt(dt))
    d = 1.0 / u
    df_step = math.exp(-r * dt)
    p = max(0.0, min(1.0, (1.0 - d) / (u - d)))

    # We need to build the full tree to get both price AND properly discounted
    # intermediate values for Greeks.  Store two time steps of the tree for FD.
    #
    # Approach: build the full tree as usual, but also compute early-step values
    # by running backwards from the terminal payoff BUT discounting all the way
    # from expiry.  The easiest correct method is to compute the option values
    # at the first two actual time-steps (t=dt and t=2*dt) by rolling backwards
    # from the terminal payoff (t=T) using the full N-step tree.
    #
    # For a European option on the tree, V(N-j, k) = expected discounted payoff
    # from node (N-j, k) to expiry, which is exactly what we get by rolling back
    # from expiry.  The CRR tree naturally gives V(0,0)=price after full
    # rollback, V(1,0)=value at t=dt after N-1 step rollback, etc.
    #
    # So we build the full tree and extract values at N, N-1, N-2 steps
    # from expiry, which correspond to t=0, t=dt, t=2*dt.

    # Build terminal payoffs at t=T (step N)
    tree_N = [0.0] * (N + 1)  # values at t=T
    for j in range(N + 1):
        F_j = F * (u**j) * (d ** (N - j))
        if option_type == OptionType.CALL:
            tree_N[j] = max(F_j - K, 0.0)
        else:
            tree_N[j] = max(K - F_j, 0.0)

    # Backwards induction: at each step we go from time (i+1)*dt to i*dt
    # tree holds values at time i*dt after processing step i
    # We need values at t=0 (after N steps), t=dt (after N-1 steps),
    # t=2*dt (after N-2 steps).

    # We'll capture the tree slice at t=2*dt first, then t=dt, then t=0.

    # Start from t=T, roll back N-2 steps to get values at t=2*dt
    tree = tree_N.copy()
    for i in range(N - 1, 1, -1):  # N-1 down to 2 => rolls back N-2 steps
        for j in range(i + 1):
            tree[j] = df_step * (p * tree[j + 1] + (1.0 - p) * tree[j])

    # tree now has N-2+1 = N-1 entries, representing values at t=2*dt
    # index j: j up-moves out of N-2 steps remaining? No — tree[j] is the
    # value at the node that has experienced j up-moves in the first 2 steps
    # plus whatever from the remaining N-2 steps. Wait, the rollback collapses
    # all remaining steps into current values.  At t=2*dt, j indexes the number
    # of up-moves in the first 2 steps (j ∈ [0, 2]). But our tree array has
    # size N-1 after N-2 backwards steps — that's because each rollback reduces
    # array size by 1. So tree now has indices 0..(N-1). These correspond to
    # nodes at t=2*dt where the node has j up-moves in the first 2 steps
    # and the remaining N-2 steps are rolled in.  But we only need the first
    # 3 nodes (j=0,1,2), since at t=2*dt there are exactly 3 possible states.

    s2 = [tree[0], tree[1], tree[2]]  # V(2,0), V(2,1), V(2,2)

    # Roll back one more step to t=dt
    for _j in range(2):  # step index goes from 1 down to 0? No — roll back step 1
        pass
    # Actually, we need to roll back from the t=2*dt state to get t=dt values.
    # tree currently holds values at t=2*dt for nodes 0..(N-1).
    # One rollback step to t=dt:
    s1_vals = [0.0] * 2  # V(1,0), V(1,1)
    for j in range(2):
        s1_vals[j] = df_step * (p * tree[j + 1] + (1.0 - p) * tree[j])

    # Roll back to t=0
    s0_val = df_step * (p * s1_vals[1] + (1.0 - p) * s1_vals[0])

    price = s0_val

    # At step 1: F*u and F*d
    F1_up = F * u
    F1_down = F * d
    delta = (s1_vals[1] - s1_vals[0]) / (F1_up - F1_down) if F1_up != F1_down else 0.0

    # At step 2: F*u^2, F, F*d^2
    F2_uu = F * u * u
    F2_ud = F  # u*d = 1
    F2_dd = F * d * d

    # Gamma via central difference at step 2, node (2,1) which is F
    dV_up = (s2[2] - s2[1]) / (F2_uu - F2_ud) if F2_uu != F2_ud else 0.0
    dV_down = (s2[1] - s2[0]) / (F2_ud - F2_dd) if F2_ud != F2_dd else 0.0
    dF_step2 = 0.5 * (F2_uu - F2_dd)
    gamma = (dV_up - dV_down) / dF_step2 if dF_step2 > 0 else 0.0

    # Theta: (V(2,1) - V(0,0)) / (2*dt)
    theta = (s2[1] - s0_val) / (2.0 * dt) if dt > 0 else 0.0

    return {
        "price": float(price),
        "delta": float(delta),
        "gamma": float(gamma),
        "theta": float(theta),
    }
