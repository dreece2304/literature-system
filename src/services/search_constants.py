"""Search Constants - Domain-specific mappings for search enhancement.

Contains acronym expansions and scientific synonyms for materials science,
semiconductor, and machine learning domains.

Usage:
    from services.search_constants import (
        ACRONYM_EXPANSIONS,
        SCIENTIFIC_SYNONYMS,
        TERM_TO_ACRONYM,
    )

    # Expand an acronym
    if "ald" in ACRONYM_EXPANSIONS:
        expansions = ACRONYM_EXPANSIONS["ald"]  # ["atomic layer deposition"]

    # Get acronym for a term
    acronym = TERM_TO_ACRONYM.get("atomic layer deposition")  # "ALD"
"""
from __future__ import annotations


# =============================================================================
# RRF (Reciprocal Rank Fusion) Constants
# =============================================================================

DEFAULT_RRF_K = 60  # Standard RRF constant
DEFAULT_ALPHA = 0.65  # Slight semantic preference (0.65 semantic, 0.35 keyword)
DEFAULT_MIN_SIMILARITY = 0.35  # Discovery-focused threshold


# =============================================================================
# Acronym Expansions
# =============================================================================

# Acronym expansions for materials science / semiconductor domain
ACRONYM_EXPANSIONS: dict[str, list[str]] = {
    # Deposition techniques
    "ald": ["atomic layer deposition"],
    "cvd": ["chemical vapor deposition"],
    "pvd": ["physical vapor deposition"],
    "mald": ["molecular atomic layer deposition"],
    "mocvd": ["metal organic chemical vapor deposition"],
    "pecvd": ["plasma enhanced chemical vapor deposition"],

    # Lithography
    "euv": ["extreme ultraviolet", "EUV lithography"],
    "duv": ["deep ultraviolet"],

    # Characterization techniques
    "xps": ["x-ray photoelectron spectroscopy"],
    "xrd": ["x-ray diffraction"],
    "sem": ["scanning electron microscopy", "scanning electron microscope"],
    "tem": ["transmission electron microscopy"],
    "afm": ["atomic force microscopy"],
    "ftir": ["fourier transform infrared"],

    # Spectroscopy
    "uv": ["ultraviolet"],
    "ir": ["infrared"],

    # Machine learning
    "ml": ["machine learning"],
    "dl": ["deep learning"],
    "nn": ["neural network", "neural networks"],
    "cnn": ["convolutional neural network"],
    "rnn": ["recurrent neural network"],

    # Simulation/Theory
    "dft": ["density functional theory"],
    "md": ["molecular dynamics"],

    # Semiconductors
    "mos": ["metal oxide semiconductor"],
    "cmos": ["complementary metal oxide semiconductor"],
    "fet": ["field effect transistor"],
    "mosfet": ["metal oxide semiconductor field effect transistor"],

    # Optoelectronics
    "led": ["light emitting diode"],
    "oled": ["organic light emitting diode"],
    "pv": ["photovoltaic", "photovoltaics"],

    # Other
    "ree": ["rare earth elements"],
    "hte": ["high throughput experimentation"],
    "doe": ["design of experiments"],
}


# =============================================================================
# Reverse Mapping: Term to Acronym
# =============================================================================

TERM_TO_ACRONYM: dict[str, str] = {}
for _acronym, _terms in ACRONYM_EXPANSIONS.items():
    for _term in _terms:
        TERM_TO_ACRONYM[_term.lower()] = _acronym.upper()


# =============================================================================
# Scientific Synonyms
# =============================================================================

# Scientific synonyms (domain-specific)
SCIENTIFIC_SYNONYMS: dict[str, list[str]] = {
    # Thin films
    "film": ["layer", "coating", "thin film"],
    "layer": ["film", "coating"],
    "coating": ["film", "layer", "deposition"],

    # Processing
    "deposition": ["growth", "coating", "synthesis"],
    "growth": ["deposition", "synthesis", "formation"],
    "synthesis": ["preparation", "fabrication", "growth"],
    "fabrication": ["synthesis", "manufacturing", "processing"],

    # Patterning
    "etching": ["removal", "patterning"],
    "patterning": ["lithography", "etching"],

    # Substrates
    "substrate": ["wafer", "support"],
    "wafer": ["substrate"],

    # Materials
    "precursor": ["reactant", "source"],
    "catalyst": ["catalytic"],
    "membrane": ["film", "barrier"],

    # Nanomaterials
    "nanoparticle": ["nanoparticles", "NP", "NPs"],
    "nanomaterial": ["nanomaterials"],

    # Lithography
    "photoresist": ["resist", "photo-resist"],
    "resist": ["photoresist"],
}
