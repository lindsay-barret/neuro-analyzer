"""Unit tests for FastSurfer segmentation QC detection.

Runnable directly with the project venv (no pytest required):
    .venv/Scripts/python.exe tests/test_quantify_qc.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from neuro_analyzer.exceptions import (
    SegmentationCorruptedError,
    SegmentationQCFailure,
)
from neuro_analyzer.quantify import _check_segmentation_qc


# Excerpts copied verbatim from the real sub-5005 deep-seg.log produced
# during the Phase 2.5 validation attempt. Used as the canonical "bad" log.
CORRUPTED_LOG = """\
[INFO: run_prediction.py:  724]: Creating brainmask based on segmentation...
[INFO: run_prediction.py:  743]: Creating aseg based on segmentation...
[INFO: run_prediction.py:  762]: Running volume-based QC check on segmentation...
[WARNING: run_prediction.py:  765]: Total segmentation volume is too small. Segmentation may be corrupted.
INFO: Running N4 bias-field correction...
None of the labels [17, 18, 26, 27, 28, 58, 59, 60, 10, 11, 12, 13, 49, 50, 51, 52, 53, 54] for merged label 10001 exist in the segmentation.
None of the labels [14, 15, 72, 24] for merged label 10003 exist in the segmentation.
None of the labels [7, 46] for merged label 10005 exist in the segmentation.
None of the labels [251, 252, 253, 254, 255] for merged label 10007 exist in the segmentation.
Partial volume stats for 100 labels written to /data/output/sub-5005/stats/aseg+DKT.stats.
"""


HEALTHY_LOG = """\
[INFO: run_prediction.py:  724]: Creating brainmask based on segmentation...
[INFO: run_prediction.py:  762]: Running volume-based QC check on segmentation...
[INFO: run_prediction.py:  769]: Segmentation volume within expected range.
INFO: Running N4 bias-field correction...
Partial volume stats for 100 labels written to /data/output/sub-5005/stats/aseg+DKT.stats.
"""


def _make_fake_subject_tree(root: Path, subject_id: str, log_content: str) -> Path:
    """Create the minimum FastSurfer subject layout containing scripts/deep-seg.log."""
    log_path = root / subject_id / "scripts" / "deep-seg.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(log_content, encoding="utf-8")
    return log_path


# Plausible non-zero, above-noise-floor, near-symmetric volumes for every
# structure in REQUIRED_SUBCORTICAL_STRUCTURES. Used as the baseline that the
# structural-completeness checks must not fire on.
_BASELINE_VOLUMES: dict[str, float] = {
    "Left-Pallidum": 1700.0,
    "Right-Pallidum": 1720.0,
    "Left-Putamen": 5000.0,
    "Right-Putamen": 5050.0,
    "Left-Caudate": 3500.0,
    "Right-Caudate": 3550.0,
    "Left-Thalamus": 7000.0,
    "Right-Thalamus": 7100.0,
    "Left-Hippocampus": 3000.0,
    "Right-Hippocampus": 3100.0,
    "Brain-Stem": 20000.0,
    "Left-Amygdala": 1500.0,
    "Right-Amygdala": 1530.0,
}


def _make_fake_aseg_stats(root: Path, subject_id: str, volumes: dict[str, float]) -> Path:
    """Write a minimal aseg+DKT.stats with the given {name: volume_mm3}.

    Real FastSurfer files have many columns; the QC parser only reads
    column 4 (volume) and column 5 (name), so we keep the layout
    minimal but column-position-faithful.
    """
    stats_path = root / subject_id / "stats" / "aseg+DKT.stats"
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Title Segmentation Statistics",
        "# Measure BrainSeg, BrainSegVol, Brain Segmentation Volume, 1100000.0, mm^3",
        "# ColHeaders Index SegId NVoxels Volume_mm3 StructName ...",
    ]
    for idx, (name, vol) in enumerate(volumes.items(), start=1):
        lines.append(f"  {idx}  0  100  {vol:.3f}  {name}  0  0  0  0  0")
    stats_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return stats_path


def test_corrupted_log_is_detected() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _make_fake_subject_tree(root, "sub-test", CORRUPTED_LOG)

        result = _check_segmentation_qc(root, "sub-test")

        assert result is not None, "QC must flag the corrupted log"
        assert isinstance(result, SegmentationQCFailure)

        # Both warning patterns appear on the same line — the regex finds two
        # matches (one per pattern), each capturing that line, so we expect 2
        # excerpts. The point is at least one fires.
        assert len(result.warning_excerpts) >= 1
        assert any("too small" in e.lower() for e in result.warning_excerpts)
        assert any("may be corrupted" in e.lower() for e in result.warning_excerpts)

        # Critical missing labels: hippocampi (17/53) and amygdalae (18/54)
        # must be in the missing set.
        assert 17 in result.missing_label_ids
        assert 53 in result.missing_label_ids
        assert 18 in result.missing_label_ids
        assert 54 in result.missing_label_ids
        # Brain-stem (16) is NOT in any "None of the labels" block of the
        # critical merged labels — should not be present.
        assert 16 not in result.missing_label_ids


def test_decoded_structures_group_lr() -> None:
    failure = SegmentationQCFailure(
        log_path=Path("/dev/null"),
        warning_excerpts=["dummy"],
        missing_label_ids={17, 53, 18, 54, 251, 255},
    )
    decoded = failure.decoded_missing_structures()
    # L/R pairs must be grouped, midline labels kept distinct.
    assert "Hippocampus L/R" in decoded
    assert "Amygdala L/R" in decoded
    assert "CC_Anterior" in decoded
    assert "CC_Posterior" in decoded
    # Make sure the raw "Left-..." form is NOT present once grouped.
    assert "Left-Hippocampus" not in decoded
    assert "Right-Hippocampus" not in decoded


def test_healthy_log_is_silent() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _make_fake_subject_tree(root, "sub-test", HEALTHY_LOG)
        result = _check_segmentation_qc(root, "sub-test")
        assert result is None


def test_missing_log_returns_none() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # Note: no scripts/deep-seg.log created.
        result = _check_segmentation_qc(root, "sub-absent")
        assert result is None


def test_exception_message_is_bilingual_and_lists_structures() -> None:
    failure = SegmentationQCFailure(
        log_path=Path("/tmp/deep-seg.log"),
        warning_excerpts=[
            "[WARNING] Total segmentation volume is too small. Segmentation may be corrupted."
        ],
        missing_label_ids={17, 53, 18, 54},
    )
    err = SegmentationCorruptedError(failure)
    msg = str(err)
    assert "ES:" in msg
    assert "EN:" in msg
    assert "Hippocampus L/R" in msg
    assert "Amygdala L/R" in msg
    assert "docs/limitations.md" in msg
    assert "exit code 3" in msg
    assert SegmentationCorruptedError.EXIT_CODE == 3


def test_only_critical_merged_labels_count() -> None:
    """After recalibration, only 2 merged labels are critical: 10001 (deep
    subcortical) and 10003 (ventricles). Other merged labels — including
    10005 (cerebellum WM) and 10007 (corpus callosum), which are produced
    by the surface pass — must not trigger QC."""
    from neuro_analyzer.quantify import _QC_CRITICAL_MERGED_LABELS
    assert _QC_CRITICAL_MERGED_LABELS == frozenset({10001, 10003})

    log = (
        "Some FastSurfer output...\n"
        "None of the labels [99] for merged label 99999 exist in the segmentation.\n"
        "All went well.\n"
    )
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _make_fake_subject_tree(root, "sub-test", log)
        result = _check_segmentation_qc(root, "sub-test")
        assert result is None, "Non-critical merged labels must not trigger QC"


# Real seg_only output emits these "None of the labels" lines for every run
# (cerebellum WM and corpus callosum are produced only by recon-surf, which
# requires a FS license). They must NOT be treated as corruption signals.
SEG_ONLY_NORMAL_LOG = """\
[INFO: run_prediction.py:  724]: Creating brainmask based on segmentation...
[INFO: run_prediction.py:  762]: Running volume-based QC check on segmentation...
INFO: Running N4 bias-field correction...
None of the labels [7, 46] for merged label 10005 exist in the segmentation.
None of the labels [251, 252, 253, 254, 255] for merged label 10007 exist in the segmentation.
Partial volume stats for 100 labels written to /data/output/sub-test/stats/aseg+DKT.stats.
"""


# ---------------------------------------------------------------------------
# Structural-completeness criteria (1: zero, 2: noise floor, 3: asymmetry)
# ---------------------------------------------------------------------------


def test_baseline_normal_pass() -> None:
    """A healthy log + a baseline aseg+DKT.stats with all required structures
    above the noise floor must not fire any QC criterion."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _make_fake_subject_tree(root, "sub-test", HEALTHY_LOG)
        _make_fake_aseg_stats(root, "sub-test", _BASELINE_VOLUMES)
        result = _check_segmentation_qc(root, "sub-test")
        assert result is None, f"Baseline must pass; got {result!r}"


def test_criterion_1_zero_pallidum_fails() -> None:
    """Pallidum L/R = 0 must trigger criterion 1 (zero volume)."""
    volumes = dict(_BASELINE_VOLUMES)
    volumes["Left-Pallidum"] = 0.0
    volumes["Right-Pallidum"] = 0.0
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _make_fake_subject_tree(root, "sub-test", HEALTHY_LOG)
        _make_fake_aseg_stats(root, "sub-test", volumes)
        result = _check_segmentation_qc(root, "sub-test")
        assert result is not None
        assert "Left-Pallidum" in result.zero_volume_structures
        assert "Right-Pallidum" in result.zero_volume_structures
        # Must NOT also list pallidum in below_noise_floor (zero takes priority)
        names_below = [n for n, _ in result.below_noise_floor]
        assert "Left-Pallidum" not in names_below
        assert "Right-Pallidum" not in names_below


def test_criterion_2_noise_floor_fails() -> None:
    """Putamen L = 85 mm³ (below 100 mm³ but non-zero) must trigger criterion 2."""
    volumes = dict(_BASELINE_VOLUMES)
    volumes["Left-Putamen"] = 85.0
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _make_fake_subject_tree(root, "sub-test", HEALTHY_LOG)
        _make_fake_aseg_stats(root, "sub-test", volumes)
        result = _check_segmentation_qc(root, "sub-test")
        assert result is not None
        assert "Left-Putamen" not in result.zero_volume_structures
        names_below = [n for n, _ in result.below_noise_floor]
        assert "Left-Putamen" in names_below
        # Verify the recorded volume is preserved
        recorded = dict(result.below_noise_floor)
        assert recorded["Left-Putamen"] == 85.0


def test_criterion_3_extreme_asymmetry_fails() -> None:
    """Thalamus L=847 / R=159 (ratio ≈ 5.3:1, above 3:1) must trigger criterion 3."""
    volumes = dict(_BASELINE_VOLUMES)
    volumes["Left-Thalamus"] = 847.0
    volumes["Right-Thalamus"] = 159.0
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _make_fake_subject_tree(root, "sub-test", HEALTHY_LOG)
        _make_fake_aseg_stats(root, "sub-test", volumes)
        result = _check_segmentation_qc(root, "sub-test")
        assert result is not None
        # Neither side is zero, so criterion 1 must NOT fire on Thalamus
        assert "Left-Thalamus" not in result.zero_volume_structures
        assert "Right-Thalamus" not in result.zero_volume_structures
        # Both sides above noise floor, so criterion 2 must NOT fire on Thalamus
        names_below = [n for n, _ in result.below_noise_floor]
        assert "Left-Thalamus" not in names_below
        assert "Right-Thalamus" not in names_below
        # Criterion 3 must fire
        pair_names = [p for p, _, _ in result.extreme_asymmetry]
        assert any("Thalamus" in p for p in pair_names)


def test_criterion_3_zero_vs_nonzero_falls_back_to_criterion_1() -> None:
    """Hippocampus L=0 / R=600: must fail via criterion 1 (Left-Hippocampus
    listed as zero), and crucially must NOT raise a ZeroDivisionError when
    computing the asymmetry ratio. The original ZeroDivisionError that
    motivated this whole QC machinery happened in exactly this configuration."""
    volumes = dict(_BASELINE_VOLUMES)
    volumes["Left-Hippocampus"] = 0.0
    volumes["Right-Hippocampus"] = 600.0
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _make_fake_subject_tree(root, "sub-test", HEALTHY_LOG)
        _make_fake_aseg_stats(root, "sub-test", volumes)
        # Must not raise.
        result = _check_segmentation_qc(root, "sub-test")
        assert result is not None
        assert "Left-Hippocampus" in result.zero_volume_structures
        assert "Right-Hippocampus" not in result.zero_volume_structures
        # The hippocampus pair must NOT appear in extreme_asymmetry — the
        # zero-side guard skips it, leaving criterion 1 as the sole signal.
        pair_names = [p for p, _, _ in result.extreme_asymmetry]
        assert not any("Hippocampus" in p for p in pair_names), (
            f"Hippocampus pair leaked into asymmetry list despite L=0: {pair_names!r}"
        )


def test_seg_only_no_false_positive() -> None:
    """A seg_only run with only 10005 and 10007 missing (and no FastSurfer
    corruption warning) must not trigger the QC check."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _make_fake_subject_tree(root, "sub-test", SEG_ONLY_NORMAL_LOG)
        result = _check_segmentation_qc(root, "sub-test")
        assert result is None, (
            "10005/10007 alone (no warning, no 10001/10003) must not fire QC: "
            f"got {result!r}"
        )


def main() -> int:
    tests = [
        test_corrupted_log_is_detected,
        test_decoded_structures_group_lr,
        test_healthy_log_is_silent,
        test_missing_log_returns_none,
        test_exception_message_is_bilingual_and_lists_structures,
        test_only_critical_merged_labels_count,
        test_seg_only_no_false_positive,
        test_baseline_normal_pass,
        test_criterion_1_zero_pallidum_fails,
        test_criterion_2_noise_floor_fails,
        test_criterion_3_extreme_asymmetry_fails,
        test_criterion_3_zero_vs_nonzero_falls_back_to_criterion_1,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
        else:
            print(f"PASS  {t.__name__}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
