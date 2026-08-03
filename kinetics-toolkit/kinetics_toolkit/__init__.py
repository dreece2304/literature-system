"""kinetics-toolkit - vapor-phase thin-film etch / dry-development kinetics.

A standalone, project-agnostic toolkit. Typical flow:

    from kinetics_toolkit import load_csv, fit_linear_parabolic, fit_arrhenius
    from kinetics_toolkit import selectivity_vs_T, fit_series_two_observable

    df = load_csv("data.csv")
    res = fit_linear_parabolic(hold_s, cleared_depth_nm)
    print(res.summary())

See README.md for the CSV schema and model definitions.
"""
from __future__ import annotations

from .models import (
    linear_parabolic_depth,
    crossover_thickness,
    arrhenius,
    thiele_modulus,
    effectiveness_factor,
    series_fractions,
    series_thickness_frac,
    series_blue_frac,
    R_GAS,
)
from .fitting import (
    FitResult,
    fit_linear_parabolic,
    fit_arrhenius,
    fit_series_two_observable,
)
from .selectivity import selectivity_vs_T, recommend_conditions
from .dataio import load_csv, compute_cleared_depth, REQUIRED_COLUMNS

__all__ = [
    "linear_parabolic_depth",
    "crossover_thickness",
    "arrhenius",
    "thiele_modulus",
    "effectiveness_factor",
    "series_fractions",
    "series_thickness_frac",
    "series_blue_frac",
    "R_GAS",
    "FitResult",
    "fit_linear_parabolic",
    "fit_arrhenius",
    "fit_series_two_observable",
    "selectivity_vs_T",
    "recommend_conditions",
    "load_csv",
    "compute_cleared_depth",
    "REQUIRED_COLUMNS",
]

__version__ = "0.1.0"
