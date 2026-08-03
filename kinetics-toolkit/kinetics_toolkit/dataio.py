"""CSV loading and schema validation.

See README.md for the full column schema.
"""
from __future__ import annotations

import pandas as pd

#: Columns that must be present in an input CSV.
REQUIRED_COLUMNS = ("state", "temperature_C", "hold_s", "thickness_nm")

#: Recognised optional columns.
OPTIONAL_COLUMNS = (
    "thickness0_nm", "k_ext", "cycles", "dose_mJ_cm2", "developer",
)

_VALID_STATES = {"exposed", "unexposed"}


def load_csv(path) -> pd.DataFrame:
    """Load and validate a measurement CSV into a DataFrame.

    Validates required columns and the ``state`` vocabulary, normalises text
    columns, and (if ``thickness0_nm`` is absent) infers the initial thickness
    per group as the value at the smallest hold time.

    Raises
    ------
    ValueError
        If required columns are missing or ``state`` contains unknown values.
    """
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"CSV missing required columns: {missing}. "
            f"Required: {list(REQUIRED_COLUMNS)}"
        )

    df["state"] = df["state"].astype(str).str.strip().str.lower()
    bad = set(df["state"].unique()) - _VALID_STATES
    if bad:
        raise ValueError(
            f"unknown state values {bad}; expected {_VALID_STATES}"
        )
    if "developer" in df.columns:
        df["developer"] = df["developer"].astype(str).str.strip().str.lower()

    if "thickness0_nm" not in df.columns:
        df = _infer_thickness0(df)
    return df


def _group_keys(df: pd.DataFrame):
    """Columns identifying one kinetic curve (everything but hold/thickness)."""
    keys = ["state", "temperature_C"]
    for opt in ("developer", "dose_mJ_cm2", "cycles"):
        if opt in df.columns:
            keys.append(opt)
    return keys


def _infer_thickness0(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``thickness0_nm`` per group as the thickness at minimum hold time."""
    keys = _group_keys(df)
    df = df.copy()

    def _t0(group):
        row = group.loc[group["hold_s"].idxmin()]
        return row["thickness_nm"]

    t0 = df.groupby(keys, dropna=False).apply(_t0).rename("thickness0_nm")
    df = df.merge(t0, left_on=keys, right_index=True, how="left")
    return df


def compute_cleared_depth(df: pd.DataFrame) -> pd.DataFrame:
    """Add a ``cleared_nm = thickness0_nm - thickness_nm`` column."""
    if "thickness0_nm" not in df.columns:
        df = _infer_thickness0(df)
    df = df.copy()
    df["cleared_nm"] = df["thickness0_nm"] - df["thickness_nm"]
    return df
