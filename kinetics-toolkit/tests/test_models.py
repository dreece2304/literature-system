"""Unit tests for the closed-form models (no fitting)."""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kinetics_toolkit import models  # noqa: E402


def test_linear_parabolic_at_zero_is_zero():
    assert models.linear_parabolic_depth(0.0, 1.0, 1.0) == pytest.approx(0.0)


def test_linear_parabolic_small_t_is_linear():
    # at small t, x ~ k_L * t
    k_L, k_P = 2.0, 1000.0
    t = 1e-3
    x = models.linear_parabolic_depth(t, k_L, k_P)
    assert x == pytest.approx(k_L * t, rel=1e-2)


def test_linear_parabolic_large_t_is_parabolic():
    # at large t, x ~ sqrt(2 k_P t)
    k_L, k_P = 100.0, 5.0
    t = 1e6
    x = models.linear_parabolic_depth(t, k_L, k_P)
    assert x == pytest.approx(np.sqrt(2 * k_P * t), rel=1e-2)


def test_crossover_thickness():
    assert models.crossover_thickness(2.0, 50.0) == pytest.approx(25.0)


def test_arrhenius_monotonic_in_T():
    T = np.array([300.0, 350.0, 400.0])
    k = models.arrhenius(T, A=1e6, Ea=50_000.0)
    assert np.all(np.diff(k) > 0)


def test_series_fractions_conserved():
    t = np.linspace(0, 50, 25)
    A, B, gas = models.series_fractions(t, k1=0.4, k2=0.05)
    assert np.allclose(A + B + gas, 1.0, atol=1e-9)
    assert np.all(A >= -1e-9) and np.all(B >= -1e-9) and np.all(gas >= -1e-9)


def test_series_degenerate_k1_equals_k2():
    # should not divide by zero and stays conserved
    t = np.linspace(0, 20, 10)
    A, B, gas = models.series_fractions(t, k1=0.2, k2=0.2)
    assert np.all(np.isfinite(B))
    assert np.allclose(A + B + gas, 1.0, atol=1e-9)


def test_series_thickness_residual_floor():
    # with a residual floor, thickness never drops below f_res
    t = np.linspace(0, 1e4, 50)
    tf = models.series_thickness_frac(t, k1=0.5, k2=0.5, residual=0.4)
    assert tf.min() >= 0.4 - 1e-9
    assert tf[-1] == pytest.approx(0.4, abs=1e-3)


def test_effectiveness_factor_limits():
    # phi -> 0  => eta -> 1 ;  large phi => eta -> 1/phi
    assert models.effectiveness_factor(1e-9) == pytest.approx(1.0, abs=1e-6)
    assert models.effectiveness_factor(50.0) == pytest.approx(1.0 / 50.0, rel=1e-3)
