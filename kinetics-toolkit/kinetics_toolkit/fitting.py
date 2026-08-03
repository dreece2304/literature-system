"""Fit routines wrapping the models in :mod:`kinetics_toolkit.models`.

Each fitter returns a :class:`FitResult` carrying parameters, 1-sigma standard
errors (from the covariance), R^2, and a human-readable ``summary()``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np
from scipy.optimize import curve_fit, least_squares

from .models import (
    linear_parabolic_depth,
    crossover_thickness,
    arrhenius_lnk,
    series_blue_frac,
    series_thickness_frac,
    R_GAS,
)


@dataclass
class FitResult:
    """Container for a fit outcome."""

    model: str
    params: Dict[str, float]
    stderr: Dict[str, float] = field(default_factory=dict)
    r2: float = float("nan")
    derived: Dict[str, float] = field(default_factory=dict)
    n: int = 0
    notes: str = ""

    def summary(self) -> str:
        lines = [f"[{self.model}]  n={self.n}  R^2={self.r2:.4f}"]
        for key, val in self.params.items():
            se = self.stderr.get(key)
            if se is not None and np.isfinite(se):
                lines.append(f"  {key:>10s} = {val:.4g}  +/- {se:.2g}")
            else:
                lines.append(f"  {key:>10s} = {val:.4g}")
        for key, val in self.derived.items():
            lines.append(f"  {key:>10s} = {val:.4g}   (derived)")
        if self.notes:
            lines.append(f"  note: {self.notes}")
        return "\n".join(lines)


def _r2(y, y_pred) -> float:
    y = np.asarray(y, dtype=float)
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")


def _stderr_from_pcov(pcov) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        return np.sqrt(np.diag(pcov))


# --------------------------------------------------------------------------- #
# Linear-parabolic depth vs hold-time
# --------------------------------------------------------------------------- #
def fit_linear_parabolic(
    t,
    x,
    p0: Optional[tuple] = None,
    film_thickness_nm: Optional[float] = None,
) -> FitResult:
    """Fit cleared depth ``x`` vs hold time ``t`` to the reverse Deal-Grove model.

    Parameters
    ----------
    t : array_like
        Hold / soak time (s).
    x : array_like
        Cleared depth / thickness loss (nm).
    p0 : (k_L, k_P), optional
        Initial guess. If None, estimated from the data.
    film_thickness_nm : float, optional
        Full film thickness; if given, the regime (reaction vs diffusion limited)
        is classified by comparing it to the crossover thickness x*.

    Returns
    -------
    FitResult with params ``k_L`` (nm/s), ``k_P`` (nm^2/s) and derived
    ``x_crossover`` (nm), plus a regime note when ``film_thickness_nm`` is given.
    """
    t = np.asarray(t, dtype=float)
    x = np.asarray(x, dtype=float)
    mask = np.isfinite(t) & np.isfinite(x)
    t, x = t[mask], x[mask]
    if t.size < 3:
        raise ValueError("need at least 3 finite (t, x) points")

    if p0 is None:
        # crude guesses: early slope -> k_L; late sqrt slope -> k_P
        order = np.argsort(t)
        t_s, x_s = t[order], x[order]
        k_L0 = max((x_s[1] - x_s[0]) / max(t_s[1] - t_s[0], 1e-9), 1e-6)
        k_P0 = max((x_s[-1] ** 2) / (2.0 * max(t_s[-1], 1e-9)), 1e-6)
        p0 = (k_L0, k_P0)

    popt, pcov = curve_fit(
        linear_parabolic_depth, t, x, p0=p0,
        bounds=([1e-12, 1e-12], [np.inf, np.inf]), maxfev=20000,
    )
    se = _stderr_from_pcov(pcov)
    k_L, k_P = float(popt[0]), float(popt[1])
    x_star = crossover_thickness(k_L, k_P)
    r2 = _r2(x, linear_parabolic_depth(t, *popt))

    note = ""
    if film_thickness_nm is not None and np.isfinite(x_star):
        ratio = film_thickness_nm / x_star
        if ratio > 3:
            note = (f"L/x* = {ratio:.1f} >> 1 -> diffusion-limited "
                    "(transport selectivity feasible)")
        elif ratio < 0.33:
            note = (f"L/x* = {ratio:.1f} << 1 -> reaction-limited "
                    "(chase chemistry, not hold/T)")
        else:
            note = f"L/x* = {ratio:.1f} -> mixed regime"

    return FitResult(
        model="linear_parabolic",
        params={"k_L": k_L, "k_P": k_P},
        stderr={"k_L": float(se[0]), "k_P": float(se[1])},
        r2=r2,
        derived={"x_crossover": float(x_star)},
        n=int(t.size),
        notes=note,
    )


# --------------------------------------------------------------------------- #
# Arrhenius
# --------------------------------------------------------------------------- #
def fit_arrhenius(T_K, k) -> FitResult:
    """Fit rate constants ``k`` at temperatures ``T_K`` (Kelvin) to Arrhenius.

    Fits the linearised form ln k = ln A - (Ea/R)(1/T) for robustness, then
    reports ``Ea`` (kJ/mol), ``A`` and their standard errors.
    """
    T_K = np.asarray(T_K, dtype=float)
    k = np.asarray(k, dtype=float)
    mask = np.isfinite(T_K) & np.isfinite(k) & (k > 0)
    T_K, k = T_K[mask], k[mask]
    if T_K.size < 2:
        raise ValueError("need at least 2 (T, k) points with k > 0")

    inv_T = 1.0 / T_K
    ln_k = np.log(k)
    popt, pcov = curve_fit(arrhenius_lnk, inv_T, ln_k,
                           p0=(ln_k.mean() + inv_T.mean() * 5000.0, 5000.0))
    se = _stderr_from_pcov(pcov)
    ln_A, Ea_over_R = float(popt[0]), float(popt[1])
    Ea_J = Ea_over_R * R_GAS
    A = float(np.exp(ln_A))
    r2 = _r2(ln_k, arrhenius_lnk(inv_T, *popt))

    return FitResult(
        model="arrhenius",
        params={"Ea_kJ_mol": Ea_J / 1000.0, "A": A},
        stderr={"Ea_kJ_mol": float(se[1] * R_GAS / 1000.0),
                "A": float(A * se[0])},
        r2=r2,
        derived={"ln_A": ln_A, "Ea_over_R_K": Ea_over_R},
        n=int(T_K.size),
    )


# --------------------------------------------------------------------------- #
# Two-observable series model (joint fit of colour + thickness)
# --------------------------------------------------------------------------- #
def fit_series_two_observable(
    t,
    thickness_frac,
    blue_frac=None,
    fit_residual: bool = False,
    p0: Optional[tuple] = None,
) -> FitResult:
    """Joint fit of A --k1--> B --k2--> volatile to two observables.

    Parameters
    ----------
    t : array_like
        Hold time (s).
    thickness_frac : array_like
        Remaining-thickness fraction (in [0, 1]); slow step k2 dominates this.
    blue_frac : array_like, optional
        Optical / colour fraction (intact chromophore, in [0, 1]); fixes the
        fast step k1. If omitted, k1 and k2 are inferred from thickness alone
        (less well constrained).
    fit_residual : bool
        If True, also fit a non-volatilisable residual floor ``f_res`` (for a
        plateauing, transport-protected film). Default False.
    p0 : tuple, optional
        Initial guess (k1, k2[, f_res]).

    Returns
    -------
    FitResult with params ``k1`` (1/s, fast/colour), ``k2`` (1/s, slow/thickness),
    optionally ``f_res``, and derived ``tau1``/``tau2`` time constants and their
    ratio ``k1/k2`` (how strongly the steps are separated).
    """
    t = np.asarray(t, dtype=float)
    thick = np.asarray(thickness_frac, dtype=float)
    has_blue = blue_frac is not None
    blue = np.asarray(blue_frac, dtype=float) if has_blue else None

    if p0 is None:
        p0 = (0.5, 0.05) + ((0.1,) if fit_residual else ())

    def residuals(params):
        if fit_residual:
            k1, k2, f_res = params
        else:
            k1, k2 = params
            f_res = 0.0
        res = thick - series_thickness_frac(t, k1, k2, residual=f_res)
        if has_blue:
            res = np.concatenate([res, blue - series_blue_frac(t, k1)])
        return res

    lb = [1e-9, 1e-9] + ([0.0] if fit_residual else [])
    ub = [np.inf, np.inf] + ([0.999] if fit_residual else [])
    sol = least_squares(residuals, x0=p0, bounds=(lb, ub), max_nfev=20000)

    # 1-sigma standard errors from the Gauss-Newton covariance approximation
    stderr_vals = _stderr_from_least_squares(sol)

    if fit_residual:
        k1, k2, f_res = (float(v) for v in sol.x)
        params = {"k1": k1, "k2": k2, "f_res": f_res}
        names = ["k1", "k2", "f_res"]
    else:
        k1, k2 = (float(v) for v in sol.x)
        params = {"k1": k1, "k2": k2}
        names = ["k1", "k2"]

    # goodness of fit on the thickness observable (the primary target)
    r2 = _r2(thick, series_thickness_frac(t, k1, k2,
                                          residual=params.get("f_res", 0.0)))
    stderr = {name: float(s) for name, s in zip(names, stderr_vals)}

    derived = {
        "tau1_s": 1.0 / k1 if k1 > 0 else float("inf"),
        "tau2_s": 1.0 / k2 if k2 > 0 else float("inf"),
        "k1_over_k2": k1 / k2 if k2 > 0 else float("inf"),
    }
    note = ("" if has_blue else
            "no colour observable supplied: k1/k2 weakly constrained")
    return FitResult(
        model="series_two_observable",
        params=params,
        stderr=stderr,
        r2=r2,
        derived=derived,
        n=int(t.size),
        notes=note,
    )


def _stderr_from_least_squares(sol) -> np.ndarray:
    """Approximate 1-sigma errors from a scipy least_squares solution."""
    n_res, n_par = sol.jac.shape
    dof = max(n_res - n_par, 1)
    chi2 = 2.0 * sol.cost  # cost = 0.5 * sum(residuals^2)
    sigma2 = chi2 / dof
    try:
        # covariance ~ sigma^2 * (J^T J)^-1
        jtj_inv = np.linalg.inv(sol.jac.T @ sol.jac)
        return np.sqrt(np.diag(jtj_inv) * sigma2)
    except np.linalg.LinAlgError:
        return np.full(n_par, np.nan)
