"""Optional plotting helpers (require matplotlib).

Imported lazily so the rest of the toolkit works without matplotlib installed.
Every function returns the matplotlib Figure so callers can save or further edit.
"""
from __future__ import annotations

import numpy as np

from .models import (
    linear_parabolic_depth,
    arrhenius,
    series_blue_frac,
    series_thickness_frac,
)


def _require_mpl():
    try:
        import matplotlib.pyplot as plt  # noqa: F401
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "matplotlib is required for kinetics_toolkit.plotting. "
            "Install it with `pip install matplotlib` "
            "(or `mamba install -n litai matplotlib`)."
        ) from exc
    return plt


def plot_linear_parabolic(t, x, fit, ax=None, label=None):
    """Scatter cleared-depth data with the fitted linear-parabolic curve."""
    plt = _require_mpl()
    t = np.asarray(t, dtype=float)
    x = np.asarray(x, dtype=float)
    if ax is None:
        _fig, ax = plt.subplots(figsize=(5, 4))
    ax.scatter(t, x, s=28, label=label or "data")
    tt = np.linspace(0, float(np.nanmax(t)) * 1.05, 200)
    ax.plot(tt, linear_parabolic_depth(tt, fit.params["k_L"], fit.params["k_P"]),
            "-", label=f"fit (x*={fit.derived['x_crossover']:.1f} nm)")
    ax.set_xlabel("hold time (s)")
    ax.set_ylabel("cleared depth (nm)")
    ax.legend()
    ax.set_title("Linear-parabolic front fit")
    return ax.figure


def plot_arrhenius(T_K, k, fit, ax=None, label=None):
    """Arrhenius plot: ln k vs 1000/T with the fitted line."""
    plt = _require_mpl()
    T_K = np.asarray(T_K, dtype=float)
    k = np.asarray(k, dtype=float)
    if ax is None:
        _fig, ax = plt.subplots(figsize=(5, 4))
    ax.scatter(1000.0 / T_K, np.log(k), s=28, label=label or "data")
    tt = np.linspace(T_K.min() * 0.97, T_K.max() * 1.03, 100)
    A = fit.params["A"]
    Ea = fit.params["Ea_kJ_mol"] * 1000.0
    ax.plot(1000.0 / tt, np.log(arrhenius(tt, A, Ea)), "-",
            label=f"Ea={fit.params['Ea_kJ_mol']:.0f} kJ/mol")
    ax.set_xlabel("1000 / T  (1/K)")
    ax.set_ylabel("ln k")
    ax.legend()
    ax.set_title("Arrhenius fit")
    return ax.figure


def plot_selectivity(pred, ax=None):
    """Plot predicted selectivity S vs temperature (output of selectivity_vs_T)."""
    plt = _require_mpl()
    if ax is None:
        _fig, ax = plt.subplots(figsize=(5, 4))
    ax.plot(pred["T_C"], pred["S"], "-")
    ax.axhline(1.0, color="grey", ls=":", lw=1)
    ax.set_xlabel("development temperature (C)")
    ax.set_ylabel("selectivity  S = R_unexp / R_exp")
    ax.set_title(f"Predicted selectivity ({pred['trend']})")
    return ax.figure


def plot_series(t, thickness_frac, blue_frac, fit, ax=None):
    """Plot the two-observable series fit (thickness + colour) vs hold time."""
    plt = _require_mpl()
    t = np.asarray(t, dtype=float)
    if ax is None:
        _fig, ax = plt.subplots(figsize=(5, 4))
    tt = np.linspace(0, float(np.nanmax(t)) * 1.05, 200)
    k1, k2 = fit.params["k1"], fit.params["k2"]
    f_res = fit.params.get("f_res", 0.0)

    ax.scatter(t, thickness_frac, s=28, color="tab:blue", label="thickness (data)")
    ax.plot(tt, series_thickness_frac(tt, k1, k2, residual=f_res), "-",
            color="tab:blue", label=f"thickness fit (k2={k2:.3g}/s)")
    if blue_frac is not None:
        ax.scatter(t, blue_frac, s=28, color="tab:orange",
                   label="colour/optical (data)")
        ax.plot(tt, series_blue_frac(tt, k1), "--", color="tab:orange",
                label=f"colour fit (k1={k1:.3g}/s)")
    ax.set_xlabel("hold time (s)")
    ax.set_ylabel("fraction remaining")
    ax.legend()
    ax.set_title("Series model: A --k1--> B --k2--> volatile")
    return ax.figure
