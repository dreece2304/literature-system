# kinetics-toolkit

Portable analysis toolkit for **vapor-phase thin-film etch / dry-development kinetics**.

It ingests endpoint (or in-situ) measurements of remaining thickness — and, optionally,
an optical-conversion observable (e.g. ellipsometric *k*, or a colour coordinate) — as a
function of **hold time, temperature, dose and cycles**, then fits transport/kinetics
models and *predicts the next experiment*:

1. **Linear–parabolic (reverse Deal–Grove)** front model → separates the
   **reaction-limited** rate constant `k_L` (nm/s) from the **diffusion-limited** rate
   constant `k_P` (nm²/s), and reports the crossover thickness `x* = k_P/k_L` that tells
   you which regime your film thickness sits in.
2. **Arrhenius** fits of `k_L(T)` and `k_P(T)` → activation energies `E_react`, `E_diff`.
3. **Selectivity prediction** `S(T) = R_unexposed(T) / R_exposed(T)` with extrapolation —
   answers *"how cold should I develop?"* before you run it.
4. **Thiele modulus** `φ` / effectiveness factor → confirms whether transport selectivity
   can exist at all for your film.
5. **Two-observable series model** `A --k1--> B --k2--> volatile` → fits a *fast* step from
   the colour/optical signal and a *slow* (rate-limiting) step from thickness loss. This is
   what quantifies a "colour change without thickness change" stall (e.g. Zn–O stripped
   fast, Zn–S volatilises slow).

> **Origin:** built for dry β-diketone (acac/tfac/hfac) development of DEZ + 4-mercaptophenol
> zincone resist, but nothing here is zincone-specific. It is a standalone package with no
> dependency on the parent repo — copy or `git mv` the whole `kinetics-toolkit/` folder into
> any project.

## Install

Core fitting needs only `numpy`, `scipy`, `pandas` (already in most sci envs).
Plotting additionally needs `matplotlib` (optional — imported lazily).

```bash
pip install -e .            # or: pip install numpy scipy pandas matplotlib
```

In the `litai` mamba env (matplotlib not yet installed):

```bash
/home/dreece23/miniforge3/bin/mamba run -n litai pip install matplotlib
```

## Quick start

```bash
# end-to-end demo on bundled synthetic data
python examples/analyze.py examples/example_data.csv
```

```python
from kinetics_toolkit import load_csv, fit_linear_parabolic, fit_arrhenius, selectivity_vs_T

df = load_csv("examples/example_data.csv")
# fit one (developer, state, temperature) group's depth-vs-hold curve
sub = df[(df.state == "unexposed") & (df.temperature_C == 90)]
res = fit_linear_parabolic(sub.hold_s, sub.thickness0_nm - sub.thickness_nm)
print(res.summary())
```

## CSV schema

One row per measurement. Required columns:

| column          | meaning                                              |
|-----------------|------------------------------------------------------|
| `state`         | `exposed` or `unexposed`                             |
| `temperature_C` | development temperature (°C)                         |
| `hold_s`        | hold / soak time (s) — the primary kinetic variable  |
| `thickness_nm`  | remaining film thickness (nm)                        |

Recommended / optional:

| column           | meaning                                                        |
|------------------|---------------------------------------------------------------|
| `thickness0_nm`  | initial thickness (nm); if absent, inferred per group at t=0   |
| `k_ext`          | optical extinction / colour-conversion observable (a.u.)       |
| `cycles`         | number of develop cycles                                       |
| `dose_mJ_cm2`    | exposure dose                                                  |
| `developer`      | developer label (e.g. `tfac`)                                  |

See `examples/example_data.csv`.

## Layout

```
kinetics-toolkit/
├── kinetics_toolkit/
│   ├── models.py        # closed-form models (pure numpy)
│   ├── fitting.py       # fit routines + FitResult dataclass
│   ├── selectivity.py   # S(T) prediction & next-experiment recommendation
│   ├── dataio.py        # CSV loader + schema validation
│   └── plotting.py      # optional matplotlib plots
├── examples/
│   ├── example_data.csv
│   ├── generate_synthetic.py
│   └── analyze.py
└── tests/
```

## Caveats (read before trusting a fit)

- **Confirm dose saturation first.** A long hold after a short reagent dose can be
  reagent-starved, so "hold time" ≠ "reaction time". Run in soak mode or verify saturation,
  otherwise `k_L`/`k_P` are meaningless.
- The linear–parabolic model assumes a single advancing front through a porous overlayer.
  A film that thins *uniformly* (reaction-limited everywhere) will fit with `x* ≫ L`.
- The series model's base form assumes eventual full removal; a true **plateau** (densified
  exposed region that never clears) shows up as `k2 → 0`. A residual-floor variant is noted
  in `models.py`.
