"""Closed-form kinetic / transport models for vapor-phase film etch & development.

All functions are pure numpy and unit-agnostic (use a consistent set, e.g. nm and s).
They are written to be safe for use as `scipy.optimize.curve_fit` model functions.

Models
------
linear_parabolic_depth : reverse Deal-Grove advancing front (reaction + diffusion).
arrhenius              : k(T) = A * exp(-Ea / (R T)).
thiele_modulus         : phi = L * sqrt(k_s / D_eff), with first-order slab effectiveness.
series_*               : A --k1--> B --k2--> volatile, for the two-observable
                         "colour change without thickness change" model.
"""
from __future__ import annotations

import numpy as np

#: Universal gas constant in J / (mol K).
R_GAS = 8.314462618


# --------------------------------------------------------------------------- #
# 1. Linear-parabolic (reverse Deal-Grove) advancing-front model
# --------------------------------------------------------------------------- #
def linear_parabolic_depth(t, k_L, k_P):
    r"""Cleared depth ``x(t)`` for a front advancing through a porous overlayer.

    Solves ``t = x/k_L + x^2/(2 k_P)`` for x:

        x(t) = sqrt((k_P/k_L)^2 + 2 k_P t) - (k_P/k_L)

    Parameters
    ----------
    t : array_like
        Hold / soak time (s).
    k_L : float
        Linear (reaction-limited) rate constant (nm/s). Dominates at small t.
    k_P : float
        Parabolic (diffusion-limited) rate constant (nm^2/s). Dominates at large t.

    Returns
    -------
    x : ndarray
        Cleared depth / thickness loss (nm).

    Notes
    -----
    Limiting behaviour:
        * small t : ``x ~ k_L t``            (reaction controlled)
        * large t : ``x ~ sqrt(2 k_P t)``    (diffusion controlled)
    The crossover thickness ``x* = k_P / k_L`` (see :func:`crossover_thickness`)
    marks where the two contributions are equal.
    """
    t = np.asarray(t, dtype=float)
    a = k_P / k_L  # = x*, the crossover thickness
    return np.sqrt(a * a + 2.0 * k_P * t) - a


def crossover_thickness(k_L, k_P):
    """Crossover thickness ``x* = k_P / k_L`` (nm).

    If your film thickness ``L`` >> x*, development is **diffusion limited**
    (transport selectivity between dense/porous regions is possible).
    If ``L`` << x*, it is **reaction limited** (selectivity must come from
    chemistry, not from hold time / temperature).
    """
    return k_P / k_L


# --------------------------------------------------------------------------- #
# 2. Arrhenius
# --------------------------------------------------------------------------- #
def arrhenius(T_K, A, Ea):
    """Arrhenius rate ``k = A * exp(-Ea / (R T))``.

    Parameters
    ----------
    T_K : array_like
        Temperature in Kelvin.
    A : float
        Pre-exponential factor (same units as k).
    Ea : float
        Activation energy in J/mol.
    """
    T_K = np.asarray(T_K, dtype=float)
    return A * np.exp(-Ea / (R_GAS * T_K))


def arrhenius_lnk(inv_T, ln_A, Ea_over_R):
    """Linearised Arrhenius for robust fitting: ``ln k = ln A - (Ea/R) * (1/T)``.

    Parameters
    ----------
    inv_T : array_like
        Reciprocal temperature 1/T (1/K).
    ln_A : float
        Natural log of the pre-exponential factor.
    Ea_over_R : float
        Activation energy divided by R (units of K).
    """
    inv_T = np.asarray(inv_T, dtype=float)
    return ln_A - Ea_over_R * inv_T


# --------------------------------------------------------------------------- #
# 3. Thiele modulus / effectiveness factor (first-order, slab)
# --------------------------------------------------------------------------- #
def thiele_modulus(L, k_s, D_eff):
    """Thiele modulus ``phi = L * sqrt(k_s / D_eff)``.

    phi >> 1  -> diffusion controlled (sharp front; dense region is protected).
    phi << 1  -> reaction controlled (uniform attack; no transport selectivity).
    """
    return L * np.sqrt(k_s / D_eff)


def effectiveness_factor(phi):
    """First-order slab effectiveness factor ``eta = tanh(phi) / phi``.

    Fraction of the film that the developer effectively reaches per unit time
    relative to the no-transport-limit case. eta -> 1 (reaction limited),
    eta -> 1/phi (strongly diffusion limited).
    """
    phi = np.asarray(phi, dtype=float)
    # guard the phi -> 0 limit (eta -> 1)
    small = np.abs(phi) < 1e-8
    safe = np.where(small, 1.0, phi)
    eta = np.where(small, 1.0, np.tanh(safe) / safe)
    return eta


# --------------------------------------------------------------------------- #
# 4. Two-observable series model:  A --k1--> B --k2--> volatile
# --------------------------------------------------------------------------- #
# Physical mapping for the zincone case:
#   A = intact Zn-O-aryl chromophore (blue).         k1 = Zn-O attack (fast).
#   B = converted, still-solid intermediate (brown). k2 = volatilisation /
#       Zn-S out-diffusion (slow, rate-limiting -> the "stall").
#   volatile (gas) = removed material -> thickness loss.
#
#   blue_frac      = A / A0          (optical / colour observable)
#   thickness_frac = (A + B) / A0    (ellipsometric thickness observable)
def series_fractions(t, k1, k2):
    """Return ``(A, B, gas)`` fractions for A --k1--> B --k2--> gas.

    Normalised so that A(0) = 1, B(0) = 0, gas(0) = 0, and A + B + gas = 1.
    Handles the ``k1 == k2`` degeneracy.
    """
    t = np.asarray(t, dtype=float)
    A = np.exp(-k1 * t)
    if np.isclose(k1, k2):
        B = k1 * t * np.exp(-k1 * t)
    else:
        B = (k1 / (k2 - k1)) * (np.exp(-k1 * t) - np.exp(-k2 * t))
    gas = 1.0 - A - B
    return A, B, gas


def series_blue_frac(t, k1):
    """Optical/colour observable: fraction of intact chromophore ``A/A0 = exp(-k1 t)``."""
    t = np.asarray(t, dtype=float)
    return np.exp(-k1 * t)


def series_thickness_frac(t, k1, k2, residual=0.0):
    """Thickness observable: ``(A + B)/A0`` (= 1 - gas), optionally on a residual floor.

    Parameters
    ----------
    t : array_like
        Hold time (s).
    k1, k2 : float
        Fast (conversion) and slow (volatilisation) rate constants (1/s).
    residual : float, optional
        Non-volatilisable fraction ``f_res`` in [0, 1) for a region that never fully
        clears (e.g. a densified, transport-protected exposed film). The thickness
        decays toward ``f_res`` instead of 0:
        ``thickness_frac = f_res + (1 - f_res) * (A + B)``.
        Default 0 (eventual full removal).
    """
    A, B, _gas = series_fractions(t, k1, k2)
    core = A + B
    return residual + (1.0 - residual) * core
