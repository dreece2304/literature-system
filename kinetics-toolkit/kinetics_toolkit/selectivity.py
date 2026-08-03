"""Selectivity prediction and next-experiment recommendation.

The contrast in a dry-developed resist (when transport/density-gated) is the ratio
of clearing rate in the unexposed (porous) vs exposed (dense) region:

    S(T) = R_unexposed(T) / R_exposed(T)
         = (A_u / A_e) * exp[ -(Ea_u - Ea_e) / (R T) ]

If Ea_unexposed < Ea_exposed, S grows as T falls -> develop colder. This module
takes the Arrhenius fits for each state and predicts S(T), then recommends a
temperature window.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np

from .models import R_GAS
from .fitting import FitResult


def _rate_at(arr: FitResult, T_K):
    """Evaluate an Arrhenius FitResult's rate at temperature(s) T_K."""
    A = arr.params["A"]
    Ea = arr.params["Ea_kJ_mol"] * 1000.0
    T_K = np.asarray(T_K, dtype=float)
    return A * np.exp(-Ea / (R_GAS * T_K))


def selectivity_vs_T(
    arr_unexposed: FitResult,
    arr_exposed: FitResult,
    T_celsius_range: Tuple[float, float] = (40.0, 130.0),
    n: int = 91,
):
    """Predict selectivity S = R_unexposed / R_exposed over a temperature range.

    Parameters
    ----------
    arr_unexposed, arr_exposed : FitResult
        Arrhenius fits (from :func:`fit_arrhenius`) for each region's rate constant.
    T_celsius_range : (lo, hi)
        Temperature span in degrees C to evaluate.
    n : int
        Number of points.

    Returns
    -------
    dict with arrays ``T_C``, ``S``, plus the rates ``R_unexposed``/``R_exposed``,
    and scalars ``dEa_kJ_mol`` (Ea_unexposed - Ea_exposed) and ``trend``.
    """
    T_C = np.linspace(T_celsius_range[0], T_celsius_range[1], n)
    T_K = T_C + 273.15
    R_u = _rate_at(arr_unexposed, T_K)
    R_e = _rate_at(arr_exposed, T_K)
    with np.errstate(divide="ignore", invalid="ignore"):
        S = R_u / R_e
    dEa = arr_unexposed.params["Ea_kJ_mol"] - arr_exposed.params["Ea_kJ_mol"]
    trend = ("colder is more selective" if dEa < 0 else
             "hotter is more selective" if dEa > 0 else
             "temperature-independent selectivity")
    return {
        "T_C": T_C,
        "S": S,
        "R_unexposed": R_u,
        "R_exposed": R_e,
        "dEa_kJ_mol": dEa,
        "trend": trend,
    }


@dataclass
class Recommendation:
    best_T_C: float
    best_S: float
    trend: str
    message: str

    def __str__(self) -> str:
        return self.message


def recommend_conditions(
    arr_unexposed: FitResult,
    arr_exposed: FitResult,
    film_thickness_nm: float,
    max_hold_s: float = 120.0,
    min_selectivity: float = 3.0,
    T_celsius_range: Tuple[float, float] = (40.0, 130.0),
) -> Recommendation:
    """Recommend a development temperature balancing selectivity and throughput.

    Picks the temperature giving the highest selectivity S at which the unexposed
    region can still be cleared within ``max_hold_s`` (i.e. R_unexposed * max_hold
    >= film_thickness). This enforces "clear the field, but as selectively as
    possible".

    Parameters
    ----------
    arr_unexposed, arr_exposed : FitResult
        Arrhenius fits for each region (rate in nm/s; use k_L fits).
    film_thickness_nm : float
        Thickness that must be cleared in the unexposed region.
    max_hold_s : float
        Largest practical hold time per the throughput budget.
    min_selectivity : float
        Selectivity target; flagged if unreachable.
    """
    pred = selectivity_vs_T(arr_unexposed, arr_exposed, T_celsius_range, n=181)
    T_C, S, R_u = pred["T_C"], pred["S"], pred["R_unexposed"]

    clears = (R_u * max_hold_s) >= film_thickness_nm
    if not np.any(clears):
        # cannot clear in budget anywhere; recommend the hottest (fastest) point
        idx = int(np.argmax(R_u))
        msg = (
            f"WARNING: unexposed cannot be cleared within {max_hold_s:.0f}s "
            f"anywhere in {T_celsius_range[0]:.0f}-{T_celsius_range[1]:.0f} C. "
            f"Hottest point T={T_C[idx]:.0f} C gives the fastest clearing "
            f"(R={R_u[idx]:.3g} nm/s, needs "
            f"{film_thickness_nm / R_u[idx]:.0f}s). Raise dose, T, or developer "
            f"strength. Trend: {pred['trend']}."
        )
        return Recommendation(float(T_C[idx]), float(S[idx]), pred["trend"], msg)

    # among temperatures that clear in budget, take the most selective
    S_ok = np.where(clears, S, -np.inf)
    idx = int(np.argmax(S_ok))
    best_T, best_S = float(T_C[idx]), float(S[idx])
    hold_needed = film_thickness_nm / R_u[idx]
    flag = "" if best_S >= min_selectivity else (
        f"  (below target S>={min_selectivity:g}; consider a developer blend or "
        "post-exposure densification to widen the density gap)")
    msg = (
        f"Recommend T = {best_T:.0f} C  ->  predicted selectivity S = {best_S:.2f}, "
        f"unexposed clears in ~{hold_needed:.0f}s (<= {max_hold_s:.0f}s budget).\n"
        f"  Selectivity trend: {pred['trend']} "
        f"(dEa = {pred['dEa_kJ_mol']:.1f} kJ/mol).{flag}"
    )
    return Recommendation(best_T, best_S, pred["trend"], msg)
