"""Domain-specific exceptions for neuro-analyzer.

THIS TOOL IS FOR RESEARCH AND EDUCATIONAL PURPOSES ONLY.
NOT INTENDED FOR CLINICAL DIAGNOSIS OR TREATMENT DECISIONS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


# FreeSurfer LUT subset — only labels we surface in user-facing messages.
# Source: $FREESURFER_HOME/FreeSurferColorLUT.txt (selected subcortical / midline).
FREESURFER_LABEL_NAMES: dict[int, str] = {
    7: "Left-Cerebellum-White-Matter",
    8: "Left-Cerebellum-Cortex",
    10: "Left-Thalamus",
    11: "Left-Caudate",
    12: "Left-Putamen",
    13: "Left-Pallidum",
    14: "3rd-Ventricle",
    15: "4th-Ventricle",
    16: "Brain-Stem",
    17: "Left-Hippocampus",
    18: "Left-Amygdala",
    24: "CSF",
    26: "Left-Accumbens",
    27: "Left-VentralDC",
    28: "Left-VentralDC",
    46: "Right-Cerebellum-White-Matter",
    47: "Right-Cerebellum-Cortex",
    49: "Right-Thalamus",
    50: "Right-Caudate",
    51: "Right-Putamen",
    52: "Right-Pallidum",
    53: "Right-Hippocampus",
    54: "Right-Amygdala",
    58: "Right-Accumbens",
    59: "Right-VentralDC",
    60: "Right-VentralDC",
    72: "5th-Ventricle",
    251: "CC_Posterior",
    252: "CC_Mid_Posterior",
    253: "CC_Central",
    254: "CC_Mid_Anterior",
    255: "CC_Anterior",
}


# Thresholds used by the structural-completeness QC criteria.
# Kept here (rather than in quantify.py) so the exception message can quote
# them without a circular import.
NOISE_FLOOR_MM3: float = 100.0
ASYMMETRY_MAX_RATIO: float = 3.0


@dataclass
class SegmentationQCFailure:
    """Structured QC failure for a FastSurfer segmentation pass.

    Carries findings from up to five criteria:
      * log-level warnings (FastSurfer's own corruption signal)
      * missing critical merged labels (10001 deep subcortical, 10003 ventricles)
      * required subcortical structures with volume = 0
      * required subcortical structures below the noise floor (< 100 mm³)
      * extreme L/R asymmetry on paired structures (ratio > 3:1)
    """

    log_path: Path
    warning_excerpts: list[str] = field(default_factory=list)
    missing_label_ids: set[int] = field(default_factory=set)
    zero_volume_structures: list[str] = field(default_factory=list)
    below_noise_floor: list[tuple[str, float]] = field(default_factory=list)
    extreme_asymmetry: list[tuple[str, float, float]] = field(default_factory=list)

    def decoded_missing_structures(self) -> list[str]:
        """Return human-readable structure names, deduplicated, L/R grouped."""
        names = sorted({
            FREESURFER_LABEL_NAMES.get(i, f"label-{i}")
            for i in self.missing_label_ids
        })
        # Group "Left-X" + "Right-X" as "X L/R"
        grouped: list[str] = []
        seen: set[str] = set()
        for n in names:
            if n in seen:
                continue
            base = None
            if n.startswith("Left-"):
                base = n[len("Left-"):]
                paired = f"Right-{base}"
            elif n.startswith("Right-"):
                base = n[len("Right-"):]
                paired = f"Left-{base}"
            else:
                grouped.append(n)
                seen.add(n)
                continue
            if paired in names:
                grouped.append(f"{base} L/R")
                seen.add(n)
                seen.add(paired)
            else:
                grouped.append(n)
                seen.add(n)
        return grouped


class SegmentationCorruptedError(RuntimeError):
    """FastSurfer's internal QC flagged the segmentation as corrupted.

    Carries a SegmentationQCFailure detailing which warnings fired and
    which anatomical labels are missing. Exit code 3 is reserved for this
    failure mode so callers can distinguish it from generic errors.
    """

    EXIT_CODE = 3

    def __init__(self, failure: SegmentationQCFailure):
        self.failure = failure
        super().__init__(self._format_message(failure))

    @staticmethod
    def _format_message(f: SegmentationQCFailure) -> str:
        sections: list[str] = []

        if f.warning_excerpts:
            joined = "\n  ".join(f.warning_excerpts)
            sections.append(f"FastSurfer warning(s):\n  {joined}")

        decoded = f.decoded_missing_structures()
        if decoded:
            sections.append(
                "Missing critical anatomical groups (merged label fully absent):\n"
                f"  {', '.join(decoded)}"
            )

        if f.zero_volume_structures:
            sections.append(
                "Required subcortical structures with zero volume:\n"
                f"  {', '.join(f.zero_volume_structures)}"
            )

        if f.below_noise_floor:
            items = ", ".join(f"{n} ({v:.1f} mm³)" for n, v in f.below_noise_floor)
            sections.append(
                f"Required structures below {NOISE_FLOOR_MM3:.0f} mm³ noise floor\n"
                f"(unambiguous segmentation failure, not biological variability):\n"
                f"  {items}"
            )

        if f.extreme_asymmetry:
            items = ", ".join(
                f"{p} (L={lh:.0f} mm³, R={rh:.0f} mm³)"
                for p, lh, rh in f.extreme_asymmetry
            )
            sections.append(
                f"Extreme L/R asymmetry (ratio > {ASYMMETRY_MAX_RATIO:.0f}:1, indicates\n"
                f"lateralized segmentation failure — biological asymmetry is typically\n"
                f"10-15% on paired subcortical structures):\n  {items}"
            )

        body = "\n\n".join(sections) if sections else "(no specific findings recorded)"

        return (
            "\n"
            "─── FastSurfer segmentation QC failed / Control de calidad fallido ───\n"
            "\n"
            "ES: La segmentación FastSurfer ha fallado al menos uno de los\n"
            "    criterios de control de calidad. Los volúmenes derivados no\n"
            "    son fiables y NO deben ser interpretados clínicamente ni\n"
            "    publicados como métricas validadas.\n"
            "\n"
            "EN: FastSurfer segmentation failed at least one QC criterion.\n"
            "    Derived volumes are unreliable and MUST NOT be interpreted\n"
            "    clinically or published as validated metrics.\n"
            "\n"
            f"{body}\n"
            "\n"
            f"Log: {f.log_path}\n"
            "\n"
            "See docs/limitations.md for known causes and the QC criteria\n"
            "definition. Process aborted with exit code "
            f"{SegmentationCorruptedError.EXIT_CODE}.\n"
        )
