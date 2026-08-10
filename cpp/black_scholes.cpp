// Black-76 pricing and Greeks — C++ hot path with pybind11.
//
// This module exposes fast, vectorised Black-76 computations used by the
// volsurface pipeline.  All functions operate on raw double arrays to avoid
// Python overhead in tight loops.
//
// Notation follows Black-76 (futures/forwards model):
//   d1 = (ln(F/K) + sigma^2 * T / 2) / (sigma * sqrt(T))
//   d2 = d1 - sigma * sqrt(T)
//   Call = df * [F * N(d1) - K * N(d2)]
//   Put  = df * [K * N(-d2) - F * N(-d1)]
//   Vega = df * F * sqrt(T) * N'(d1)

#include <cmath>
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <stdexcept>
#include <string>
#include <vector>

namespace py = pybind11;

// ---------------------------------------------------------------------------
// Numerical constants
// ---------------------------------------------------------------------------

static constexpr double SQRT2PI = 2.5066282746310002;   // sqrt(2*pi)
static constexpr double M_1_SQRT2 = 0.7071067811865475;  // 1/sqrt(2)

// ---------------------------------------------------------------------------
// Standard normal CDF via erf (Abramowitz & Stegun 7.1.26)
// ---------------------------------------------------------------------------

inline double norm_cdf(double x) noexcept {
    return 0.5 * (1.0 + std::erf(x * M_1_SQRT2));
}

inline double norm_pdf(double x) noexcept {
    return std::exp(-0.5 * x * x) / SQRT2PI;
}

// ---------------------------------------------------------------------------
// Single-option pricing (scalar entry point)
// ---------------------------------------------------------------------------

double black76_price_scalar(double F, double K, double sigma, double T,
                            double df, int option_type) {
    if (sigma <= 0.0 || T <= 0.0 || F <= 0.0 || K <= 0.0) {
        if (option_type == 1)  // CALL
            return df * std::max(F - K, 0.0);
        else
            return df * std::max(K - F, 0.0);
    }
    double sigma_sqrt_T = sigma * std::sqrt(T);
    double d1 = std::log(F / K) / sigma_sqrt_T + 0.5 * sigma_sqrt_T;
    double d2 = d1 - sigma_sqrt_T;
    if (option_type == 1)  // CALL
        return df * (F * norm_cdf(d1) - K * norm_cdf(d2));
    else
        return df * (K * norm_cdf(-d2) - F * norm_cdf(-d1));
}

// ---------------------------------------------------------------------------
// Vectorised price + all Greeks (one pass over the data)
// ---------------------------------------------------------------------------
// Returns a tuple of 6 arrays: (price, delta, gamma, vega, theta, rho).
// All arrays are the same length as the inputs.
//
// Greeks returned are the *discounted* standard sensitivities:
//   delta = df * dCall/dF  (or dPut/dF)
//   gamma = df * d2Call/dF2
//   vega  = df * dCall/dsigma
//   theta = dCall/dT  (time decay including discounting)
//   rho   = dCall/dr  = -T * price

py::tuple black76_price_greeks_vectorized(
    py::array_t<double, py::array::c_style> F_arr,
    py::array_t<double, py::array::c_style> K_arr,
    py::array_t<double, py::array::c_style> sigma_arr,
    py::array_t<double, py::array::c_style> T_arr,
    py::array_t<double, py::array::c_style> r_arr,
    int option_type) {

    auto F = F_arr.unchecked<1>();
    auto K = K_arr.unchecked<1>();
    auto sigma = sigma_arr.unchecked<1>();
    auto T = T_arr.unchecked<1>();
    auto r = r_arr.unchecked<1>();

    auto n = static_cast<size_t>(F.shape(0));

    if (K.shape(0) != n || sigma.shape(0) != n ||
        T.shape(0) != n || r.shape(0) != n) {
        throw std::runtime_error("All input arrays must have the same length.");
    }

    py::array_t<double> price_arr(n);
    py::array_t<double> delta_arr(n);
    py::array_t<double> gamma_arr(n);
    py::array_t<double> vega_arr(n);
    py::array_t<double> theta_arr(n);
    py::array_t<double> rho_arr(n);

    auto p_price = price_arr.mutable_unchecked<1>();
    auto p_delta = delta_arr.mutable_unchecked<1>();
    auto p_gamma = gamma_arr.mutable_unchecked<1>();
    auto p_vega = vega_arr.mutable_unchecked<1>();
    auto p_theta = theta_arr.mutable_unchecked<1>();
    auto p_rho = rho_arr.mutable_unchecked<1>();

    bool is_call = (option_type == 1);

    for (size_t i = 0; i < n; ++i) {
        double Fi = F(i), Ki = K(i), sigmai = sigma(i);
        double Ti = T(i), ri = r(i);

        if (sigmai <= 0.0 || Ti <= 0.0 || Fi <= 0.0 || Ki <= 0.0) {
            double df = std::exp(-ri * Ti);
            double intrinsic;
            if (is_call) {
                intrinsic = df * std::max(Fi - Ki, 0.0);
                p_price(i) = intrinsic;
                p_delta(i) = (Fi > Ki) ? df : 0.0;
            } else {
                intrinsic = df * std::max(Ki - Fi, 0.0);
                p_delta(i) = (Ki > Fi) ? -df : 0.0;
            }
            p_gamma(i) = 0.0;
            p_vega(i) = 0.0;
            p_theta(i) = 0.0;
            p_rho(i) = -Ti * intrinsic;
            continue;
        }

        double sqrt_t = std::sqrt(Ti);
        double sigma_sqrt_T = sigmai * sqrt_t;
        double d1 = std::log(Fi / Ki) / sigma_sqrt_T + 0.5 * sigma_sqrt_T;
        double d2 = d1 - sigma_sqrt_T;
        double df = std::exp(-ri * Ti);
        double npd1 = norm_pdf(d1);

        double price, delta, gamma, vega, theta, rho;

        if (is_call) {
            double nd1 = norm_cdf(d1);
            double nd2 = norm_cdf(d2);
            price = df * (Fi * nd1 - Ki * nd2);
            delta = df * nd1;
            vega = df * Fi * sqrt_t * npd1;
            theta = -Fi * sigmai * npd1 / (2.0 * sqrt_t) * df
                    + ri * Fi * nd1 * df
                    - ri * Ki * nd2 * df;
        } else {
            double nd1 = norm_cdf(d1);
            double nd2 = norm_cdf(d2);
            double nnd1 = 1.0 - nd1;
            double nnd2 = 1.0 - nd2;
            price = df * (Ki * nnd2 - Fi * nnd1);
            delta = df * (nd1 - 1.0);
            vega = df * Fi * sqrt_t * npd1;
            theta = -Fi * sigmai * npd1 / (2.0 * sqrt_t) * df
                    - ri * Fi * nnd1 * df
                    + ri * Ki * nnd2 * df;
        }
        gamma = df * npd1 / (Fi * sigma_sqrt_T);
        rho = -Ti * price;

        p_price(i) = price;
        p_delta(i) = delta;
        p_gamma(i) = gamma;
        p_vega(i) = vega;
        p_theta(i) = theta;
        p_rho(i) = rho;
    }

    return py::make_tuple(price_arr, delta_arr, gamma_arr,
                          vega_arr, theta_arr, rho_arr);
}

// ---------------------------------------------------------------------------
// Module definition
// ---------------------------------------------------------------------------

PYBIND11_MODULE(_core, m) {
    m.doc() = "C++ hot path for Black-76 pricing and Greeks.";
    m.def("black76_price",
          &black76_price_scalar,
          py::arg("F"), py::arg("K"), py::arg("sigma"),
          py::arg("T"), py::arg("df"), py::arg("option_type"),
          "Scalar Black-76 price.  option_type: 1=CALL, 0=PUT.  "
          "df is the discount factor exp(-rT).");
    m.def("black76_price_greeks_vectorized",
          &black76_price_greeks_vectorized,
          py::arg("F"), py::arg("K"), py::arg("sigma"),
          py::arg("T"), py::arg("r"), py::arg("option_type"),
          "Vectorised Black-76 price + all Greeks.  "
          "Returns (price, delta, gamma, vega, theta, rho) as numpy arrays.");
}