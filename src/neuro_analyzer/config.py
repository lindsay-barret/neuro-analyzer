"""Configuration and constants for Neuro-Analyzer."""

from pathlib import Path
from dataclasses import dataclass

# --- API ---
API_MODEL = "claude-sonnet-4-20250514"
API_MAX_TOKENS = 2000
API_MAX_RETRIES = 3
API_RETRY_BACKOFF = 2.0  # seconds, multiplied at each retry

# --- Slice selection ---
# Number of slices per plane and sequence
SLICE_COUNTS = {
    "t1_axial": 22,
    "t1_coronal": 12,
    "t1_sagittal": 8,
    "swi_axial": 12,
}

# Focal region of interest (proportion of the volume along the plane's main axis)
# 0.0 = brain base / anterior / left, 1.0 = vertex / posterior / right
# Default targets the upper-frontal region; tunable per case.
FRONTAL_FOCUS_RANGE = (0.25, 0.85)

# Sampling density in the focal zone vs out-of-zone
FOCAL_DENSITY_RATIO = 3  # 3x more slices in the focal zone

# --- Rendu PNG ---
PNG_DPI = 150
PNG_SIZE_INCHES = (6, 6)
WINDOW_LEVEL_T1 = {"center": 600, "width": 1200}  # Ajustable
WINDOW_LEVEL_SWI = {"center": 300, "width": 600}

# --- DICOM sequences to look for ---
# Patterns to identify sequences by SeriesDescription or ProtocolName
SEQUENCE_PATTERNS = {
    "t1_3d": [
        "t1w_3d", "t1_3d", "3d_t1", "mprage", "bravo", "tfe", "spgr",
        "t1w_tfe", "st1w", "ir_fspgr", "3d_tfe",
    ],
    "t2": [
        "t2w", "t2_", "_t2", "t2 ", "tse_t2",
    ],
    "flair": [
        "flair", "dark_fluid", "dark-fluid",
    ],
    "swi": [
        "swi", "susceptibility", "swan", "venobold",
    ],
    "dwi": [
        "dwi", "diffusion", "dti", "diff_",
    ],
    "localizer": [
        "survey", "scout", "localizer", "loc_",
    ],
}


# =====================================================================
# Patient context loading
# =====================================================================
# The pipeline accepts an optional YAML context file describing the
# specific case under analysis (clinical question, suspected diagnosis,
# per-sequence notes, optional clinical correlation prose). When no
# file is provided, the pipeline falls back to generic, unbiased prompts
# and reports — see docstrings in vision_analyzer._build_prompt and
# report_generator for fallback behavior.
#
# IMPORTANT: real patient context files MUST stay on the user's machine
# and MUST NOT be committed. The .gitignore in this repo blocks files
# matching `*-context.yaml`, `*-context.yml`, `*-context.json`,
# `patient-context.*`, and any case-specific `<name>-context.*`
# variant.
# =====================================================================

CONTEXT_ENV_VAR = "PATIENT_CONTEXT_FILE"

EXAMPLE_CONTEXT_PATH = "examples/example-context.yaml"

# Fallback prompt fragments used when the context file is absent or a
# given field is missing. Generic, unbiased phrasing — see the docstring
# of vision_analyzer._build_prompt for the rationale.
DEFAULT_DIAGNOSTIC_FOCUS = (
    "Analyze this slice and look for any structural abnormality, "
    "asymmetry, gyrification anomaly, or signal abnormality. Do not "
    "presuppose any diagnosis — describe what you observe."
)

DEFAULT_SEQUENCE_NOTES = {
    "swi": (
        "For SWI sequences, report any focal hypointensity "
        "(microhemorrhage, calcification, venous abnormality) and any "
        "signal asymmetry."
    ),
}


def load_patient_context(path: Path | str | None) -> dict:
    """Load a patient context YAML file.

    Args:
        path: Path to a YAML file. If None, returns an empty dict and the
            pipeline will use generic fallbacks throughout.

    Returns:
        A dict with optional keys: ``patient_context``, ``diagnostic_focus``,
        ``sequence_specific_notes`` (dict keyed by sequence name),
        ``clinical_correlation`` (dict, optional sub-keys ``eeg``,
        ``development``, plus arbitrary user keys).

    Raises:
        FileNotFoundError: if ``path`` is provided but does not exist. The
            error message points at ``examples/example-context.yaml`` as a
            template the user can copy and adapt.
        ValueError: if the YAML is malformed.
    """
    if path is None:
        return {}

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Patient context file not found: {p}\n"
            f"See {EXAMPLE_CONTEXT_PATH} for the expected structure, "
            f"or run without --context-file to use generic fallbacks."
        )

    try:
        import yaml  # PyYAML, listed in requirements
    except ImportError as e:
        raise ImportError(
            "Loading a patient context file requires PyYAML. "
            "Install with: pip install pyyaml"
        ) from e

    try:
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ValueError(
            f"Malformed YAML in {p}: {e}\n"
            f"See {EXAMPLE_CONTEXT_PATH} for a valid template."
        ) from e

    if not isinstance(data, dict):
        raise ValueError(
            f"Patient context file must be a YAML mapping at the top level, "
            f"got {type(data).__name__}. See {EXAMPLE_CONTEXT_PATH}."
        )

    return data


@dataclass
class AnalysisConfig:
    """Configuration for an analysis."""
    input_dir: Path
    output_dir: Path | None = None
    max_slices: int | None = None
    model: str = API_MODEL
    verbose: bool = False
    skip_conversion: bool = False
    skip_analysis: bool = False
    context_file: Path | None = None

    def __post_init__(self):
        self.input_dir = Path(self.input_dir)
        if self.output_dir is None:
            self.output_dir = self.input_dir / "neuro_analysis"
        else:
            self.output_dir = Path(self.output_dir)
        if self.context_file is not None:
            self.context_file = Path(self.context_file)

    @property
    def nifti_dir(self) -> Path:
        return self.output_dir / "nifti"

    @property
    def slices_dir(self) -> Path:
        return self.output_dir / "slices"

    @property
    def analysis_dir(self) -> Path:
        return self.output_dir / "analysis"

    @property
    def report_path(self) -> Path:
        return self.output_dir / "report.md"

    @property
    def inventory_path(self) -> Path:
        return self.output_dir / "inventory.json"

    def ensure_dirs(self):
        """Create all output directories."""
        for d in [self.output_dir, self.nifti_dir, self.slices_dir, self.analysis_dir]:
            d.mkdir(parents=True, exist_ok=True)
