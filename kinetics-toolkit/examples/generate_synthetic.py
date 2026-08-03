"""Generate reproducible synthetic datasets for the demos and tests.

Writes two CSVs next to this script:

* ``example_data.csv``  - depth-vs-hold at several temperatures for exposed and
  unexposed regions, following the linear-parabolic front model with
  Arrhenius-distributed rate constants (unexposed has the LOWER activation
  energy -> colder is more selective). Drives the linear-parabolic + Arrhenius +
  selectivity demo.

* ``example_series.csv`` - a single-temperature "colour change without thickness
  change" dataset following the A->B->volatile series model, with the exposed
  region plateauing (residual floor). Drives the two-observable series demo.

Run:  python examples/generate_synthetic.py
"""
from __future__ import annotations

import os
import numpy as np

# allow running from anywhere
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kinetics_toolkit.models import (  # noqa: E402
    linear_parabolic_depth, arrhenius, series_thickness_frac, series_blue_frac,
)

HERE = os.path.dirname(os.path.abspath(__file__))
FILM_NM = 50.0

# Arrhenius parameters for the linear rate constant k_L (nm/s).
# unexposed (porous) has the lower barrier -> selectivity improves as T falls.
# Rates are tuned so the cleared depth stays below the film thickness across the
# hold window (no censored/fully-cleared points), keeping the k_L fits clean.
ARRH = {
    "unexposed": dict(A=5.4e4, Ea_kJ=35.0, x_star=20.0),  # x* = k_P/k_L (nm)
    "exposed":   dict(A=4.6e7, Ea_kJ=60.0, x_star=8.0),
}
TEMPS_C = [70.0, 90.0, 110.0]
HOLDS_S = [2.0, 5.0, 10.0, 20.0, 40.0, 80.0]


def _gen_depth_dataset(rng):
    rows = ["state,developer,temperature_C,hold_s,thickness0_nm,thickness_nm,k_ext"]
    for state, p in ARRH.items():
        for T_C in TEMPS_C:
            T_K = T_C + 273.15
            k_L = float(arrhenius(T_K, p["A"], p["Ea_kJ"] * 1000.0))
            k_P = p["x_star"] * k_L
            # a fast colour-conversion rate (just for a realistic k_ext column)
            k1 = 0.12 * (T_K / 383.15)
            for t in HOLDS_S:
                cleared = float(linear_parabolic_depth(t, k_L, k_P))
                cleared = min(cleared, FILM_NM)
                thick = FILM_NM - cleared + rng.normal(0, 0.4)
                thick = max(thick, 0.0)
                blue = float(series_blue_frac(t, k1))
                k_ext = 0.04 + 0.45 * blue + rng.normal(0, 0.01)
                rows.append(
                    f"{state},tfac,{T_C:.0f},{t:.0f},{FILM_NM:.0f},"
                    f"{thick:.2f},{k_ext:.4f}"
                )
    return "\n".join(rows) + "\n"


def _gen_series_dataset(rng):
    holds = [1.0, 2.0, 4.0, 8.0, 15.0, 30.0, 60.0, 120.0]
    # unexposed: clears fully (k2 finite); exposed: plateaus (residual floor)
    cfg = {
        "unexposed": dict(k1=0.40, k2=0.060, res=0.0),
        "exposed":   dict(k1=0.40, k2=0.005, res=0.55),
    }
    rows = ["state,developer,temperature_C,hold_s,thickness0_nm,thickness_nm,k_ext"]
    for state, c in cfg.items():
        for t in holds:
            tf = float(series_thickness_frac(t, c["k1"], c["k2"], residual=c["res"]))
            thick = FILM_NM * tf + rng.normal(0, 0.4)
            blue = float(series_blue_frac(t, c["k1"]))
            k_ext = 0.03 + 0.50 * blue + rng.normal(0, 0.008)
            rows.append(
                f"{state},acac,110,{t:.0f},{FILM_NM:.0f},{thick:.2f},{k_ext:.4f}"
            )
    return "\n".join(rows) + "\n"


def main():
    rng = np.random.default_rng(20260613)
    with open(os.path.join(HERE, "example_data.csv"), "w") as fh:
        fh.write(_gen_depth_dataset(rng))
    with open(os.path.join(HERE, "example_series.csv"), "w") as fh:
        fh.write(_gen_series_dataset(rng))
    print("wrote example_data.csv and example_series.csv")


if __name__ == "__main__":
    main()
