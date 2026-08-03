"""Round-trip tests: generate data from a model with known parameters, fit,
and assert the parameters are recovered."""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kinetics_toolkit import (  # noqa: E402
    models, fit_linear_parabolic, fit_arrhenius, fit_series_two_observable,
    selectivity_vs_T, recommend_conditions,
)


def test_recover_linear_parabolic():
    rng = np.random.default_rng(0)
    k_L, k_P = 1.5, 40.0
    t = np.array([1, 2, 5, 10, 20, 40, 80, 160], dtype=float)
    x = models.linear_parabolic_depth(t, k_L, k_P) + rng.normal(0, 0.05, t.size)
    fit = fit_linear_parabolic(t, x, film_thickness_nm=50.0)
    assert fit.params["k_L"] == pytest.approx(k_L, rel=0.1)
    assert fit.params["k_P"] == pytest.approx(k_P, rel=0.1)
    assert fit.r2 > 0.99
    assert "x_crossover" in fit.derived


def test_recover_arrhenius():
    A, Ea = 1.0e6, 45_000.0
    T_K = np.array([300.0, 320.0, 340.0, 360.0, 380.0])
    k = models.arrhenius(T_K, A, Ea)
    fit = fit_arrhenius(T_K, k)
    assert fit.params["Ea_kJ_mol"] == pytest.approx(Ea / 1000.0, rel=1e-3)
    assert fit.params["A"] == pytest.approx(A, rel=1e-2)


def test_recover_series_two_observable():
    rng = np.random.default_rng(1)
    k1, k2 = 0.4, 0.04
    t = np.array([1, 2, 4, 8, 15, 30, 60, 120], dtype=float)
    thick = models.series_thickness_frac(t, k1, k2) + rng.normal(0, 0.01, t.size)
    blue = models.series_blue_frac(t, k1) + rng.normal(0, 0.01, t.size)
    fit = fit_series_two_observable(t, thick, blue)
    assert fit.params["k1"] == pytest.approx(k1, rel=0.2)
    assert fit.params["k2"] == pytest.approx(k2, rel=0.2)
    # the fast colour step should be clearly separated from slow thickness step
    assert fit.derived["k1_over_k2"] > 3


def test_recover_series_with_residual_plateau():
    rng = np.random.default_rng(2)
    k1, k2, f_res = 0.4, 0.02, 0.5
    t = np.array([1, 2, 4, 8, 15, 30, 60, 120, 240], dtype=float)
    thick = models.series_thickness_frac(t, k1, k2, residual=f_res) \
        + rng.normal(0, 0.008, t.size)
    blue = models.series_blue_frac(t, k1) + rng.normal(0, 0.008, t.size)
    fit = fit_series_two_observable(t, thick, blue, fit_residual=True)
    assert fit.params["f_res"] == pytest.approx(f_res, abs=0.08)


def test_selectivity_colder_is_better_when_unexposed_has_lower_Ea():
    # unexposed lower Ea -> S should rise as T falls
    T_K = np.array([343.15, 363.15, 383.15])
    k_unexp = models.arrhenius(T_K, 1.2e5, 35_000.0)
    k_exp = models.arrhenius(T_K, 4.6e7, 60_000.0)
    fu = fit_arrhenius(T_K, k_unexp)
    fe = fit_arrhenius(T_K, k_exp)
    pred = selectivity_vs_T(fu, fe, T_celsius_range=(40, 130))
    # selectivity at the cold end exceeds the hot end
    assert pred["S"][0] > pred["S"][-1]
    assert "colder" in pred["trend"]


def test_recommendation_runs_and_clears():
    T_K = np.array([343.15, 363.15, 383.15])
    fu = fit_arrhenius(T_K, models.arrhenius(T_K, 1.2e5, 35_000.0))
    fe = fit_arrhenius(T_K, models.arrhenius(T_K, 4.6e7, 60_000.0))
    rec = recommend_conditions(fu, fe, film_thickness_nm=50.0, max_hold_s=120.0)
    assert np.isfinite(rec.best_T_C)
    assert np.isfinite(rec.best_S)
    assert isinstance(str(rec), str)
