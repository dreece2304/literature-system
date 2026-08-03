"""End-to-end demo: fit kinetics, predict selectivity, recommend next experiment.

Usage:
    python examples/analyze.py [example_data.csv] [example_series.csv]

If files are omitted it uses the bundled examples (generating them if needed).
Saves plots to ./figures/ when matplotlib is available; otherwise prints only.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kinetics_toolkit import (  # noqa: E402
    load_csv, compute_cleared_depth, fit_linear_parabolic, fit_arrhenius,
    selectivity_vs_T, recommend_conditions, fit_series_two_observable,
)

HERE = os.path.dirname(os.path.abspath(__file__))
FILM_NM = 50.0


def _ensure_examples():
    data = os.path.join(HERE, "example_data.csv")
    series = os.path.join(HERE, "example_series.csv")
    if not (os.path.exists(data) and os.path.exists(series)):
        import generate_synthetic
        generate_synthetic.main()
    return data, series


def _try_plots():
    try:
        import matplotlib  # noqa: F401
        return True
    except ImportError:
        print("\n(matplotlib not installed -> skipping plots; "
              "`pip install matplotlib` to enable)")
        return False


def main(argv):
    data_csv = argv[1] if len(argv) > 1 else None
    series_csv = argv[2] if len(argv) > 2 else None
    if data_csv is None or series_csv is None:
        d, s = _ensure_examples()
        data_csv = data_csv or d
        series_csv = series_csv or s

    # ----- 1. linear-parabolic fit per (state, temperature) -----------------
    print("=" * 70)
    print("1) LINEAR-PARABOLIC FRONT FITS  (cleared depth vs hold time)")
    print("=" * 70)
    df = compute_cleared_depth(load_csv(data_csv))
    arr_rates = {"unexposed": {}, "exposed": {}}
    for (state, T_C), g in df.groupby(["state", "temperature_C"]):
        # Drop censored (fully-cleared) points: once thickness hits ~0 the
        # measurement is a lower bound on the front, not a rate point, and it
        # biases the linear-parabolic fit. Keep only uncensored data.
        uncensored = g[g["cleared_nm"] < 0.97 * FILM_NM]
        if len(uncensored) < 3:
            print(f"\n{state} @ {T_C:.0f} C  -> skipped "
                  f"({len(uncensored)} uncensored pts; reduce hold or dose)")
            continue
        fit = fit_linear_parabolic(
            uncensored["hold_s"], uncensored["cleared_nm"],
            film_thickness_nm=FILM_NM)
        arr_rates[state][T_C] = fit.params["k_L"]
        print(f"\n{state} @ {T_C:.0f} C")
        print(fit.summary())

    # ----- 2. Arrhenius per state on k_L ------------------------------------
    print("\n" + "=" * 70)
    print("2) ARRHENIUS FITS of k_L(T)")
    print("=" * 70)
    arr_fits = {}
    for state, by_T in arr_rates.items():
        T_K = [T + 273.15 for T in by_T]
        k = list(by_T.values())
        arr_fits[state] = fit_arrhenius(T_K, k)
        print(f"\n{state}")
        print(arr_fits[state].summary())

    # ----- 3. selectivity prediction + recommendation -----------------------
    print("\n" + "=" * 70)
    print("3) SELECTIVITY PREDICTION  S(T) = R_unexposed / R_exposed")
    print("=" * 70)
    pred = selectivity_vs_T(arr_fits["unexposed"], arr_fits["exposed"])
    print(f"trend: {pred['trend']}   dEa = {pred['dEa_kJ_mol']:.1f} kJ/mol")
    for T, S in zip(pred["T_C"][::20], pred["S"][::20]):
        print(f"   T={T:6.1f} C   S={S:6.2f}")
    rec = recommend_conditions(
        arr_fits["unexposed"], arr_fits["exposed"],
        film_thickness_nm=FILM_NM, max_hold_s=120.0, min_selectivity=10.0)
    print("\nRECOMMENDATION:\n  " + str(rec).replace("\n", "\n  "))

    # ----- 4. two-observable series fit (colour vs thickness) ---------------
    print("\n" + "=" * 70)
    print("4) SERIES MODEL  A --k1--> B --k2--> volatile  (colour vs thickness)")
    print("=" * 70)
    sdf = load_csv(series_csv)
    for state, g in sdf.groupby("state"):
        g = g.sort_values("hold_s")
        t = g["hold_s"].to_numpy()
        thick_frac = (g["thickness_nm"] / g["thickness0_nm"]).to_numpy()
        blue = g["k_ext"].to_numpy()
        blue_frac = (blue - blue.min()) / (blue.max() - blue.min())
        fit = fit_series_two_observable(
            t, thick_frac, blue_frac, fit_residual=(state == "exposed"))
        print(f"\n{state}")
        print(fit.summary())

    # ----- 5. optional plots ------------------------------------------------
    if _try_plots():
        import matplotlib
        matplotlib.use("Agg")
        from kinetics_toolkit import plotting
        figdir = os.path.join(HERE, "figures")
        os.makedirs(figdir, exist_ok=True)
        fig = plotting.plot_selectivity(pred)
        fig.savefig(os.path.join(figdir, "selectivity.png"), dpi=130,
                    bbox_inches="tight")
        print(f"\nsaved figures to {figdir}/")


if __name__ == "__main__":
    main(sys.argv)
