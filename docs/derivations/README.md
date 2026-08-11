# Derivations

Full first-principles derivations of every non-obvious formula used in
VolFoundry.  These documents provide the mathematical foundation for the
implementation and are intended for researchers, students, and developers
who want to verify or extend the library.

Each derivation follows a standard structure:

| Section | Content |
|---------|---------|
| **Definition** | What is being derived |
| **Assumptions** | Conditions under which the derivation is valid |
| **Formula** | The key result |
| **Implementation** | How VolFoundry implements it |
| **Numerical caveats** | Known edge cases and failure modes |
| **References** | Primary literature |

## Available derivations

| Document | Content |
|----------|---------|
| [vega.md](vega.md) | Black-76 vega (∂C/∂σ) — first-principles derivation with d₁/d₂ identities |
| [svi.md](svi.md) | Raw SVI parameterization — w(k), w'(k), w''(k), wing asymptotics, Lee bound |
| [ssvi.md](ssvi.md) | SSVI surface — functional form, φ(θ) power law, calendar-free proof sketch, Lee bound |
| [arbitrage.md](arbitrage.md) | Butterfly g(k), calendar monotonicity, Breeden–Litzenberger density — full formulas and limit analysis |

## See also

- [Concepts directory](../concepts/) — high-level explanations with less mathematical depth
- [API reference](../api/) — how to use the implemented functions
- [Architecture overview](../development/architecture.md)