"""Quantitative analysis via FastSurfer (Docker): regional volumetry, cortical thickness, LGI."""

import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .disclaimer import as_markdown_blockquote
from .exceptions import (
    ASYMMETRY_MAX_RATIO,
    NOISE_FLOOR_MM3,
    SegmentationQCFailure,
)

logger = logging.getLogger(__name__)

# Merged-label IDs in segstats whose absence indicates a structurally broken
# segmentation. Only labels predicted by the deep CNN are checked:
#   10001 — deep subcortical (hippocampus, amygdala, thalamus, basal ganglia)
#   10003 — ventricles (3rd, 4th, 5th, CSF)
# Excluded: 10005 (cerebellum WM, FS labels 7/46) and 10007 (corpus callosum,
# FS labels 251-255). These are produced by the recon-surf surface pass which
# requires a FreeSurfer license and is not run in the default seg_only mode;
# their absence is expected and does not indicate corruption.
_QC_CRITICAL_MERGED_LABELS: frozenset[int] = frozenset({10001, 10003})

_QC_WARNING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Total segmentation volume is too small", re.IGNORECASE),
    re.compile(r"Segmentation may be corrupted", re.IGNORECASE),
)

_QC_NONE_OF_LABELS_RE = re.compile(
    r"None of the labels \[([\d,\s]+)\] for merged label (\d+)",
    re.IGNORECASE,
)

# Required subcortical structures for the structural-completeness QC.
# A volume of zero on any of these — or a value below the noise floor —
# is treated as a hard segmentation failure regardless of what the
# FastSurfer log says.
#
# This list is deliberately scoped to deep-CNN outputs (no surface-only
# labels). It is NOT a validation against pediatric norms — see the
# docstring of _check_structural_completeness for the noise-floor rationale.
REQUIRED_SUBCORTICAL_STRUCTURES: tuple[str, ...] = (
    "Left-Pallidum", "Right-Pallidum",
    "Left-Putamen", "Right-Putamen",
    "Left-Caudate", "Right-Caudate",
    "Left-Thalamus", "Right-Thalamus",
    "Left-Hippocampus", "Right-Hippocampus",
    "Brain-Stem",
    "Left-Amygdala", "Right-Amygdala",
)

# Pairs evaluated for L/R asymmetry. Brain-Stem is intentionally excluded
# (midline structure, no contralateral counterpart).
_PAIRED_SUBCORTICAL: tuple[tuple[str, str], ...] = (
    ("Left-Pallidum", "Right-Pallidum"),
    ("Left-Putamen", "Right-Putamen"),
    ("Left-Caudate", "Right-Caudate"),
    ("Left-Thalamus", "Right-Thalamus"),
    ("Left-Hippocampus", "Right-Hippocampus"),
    ("Left-Amygdala", "Right-Amygdala"),
)


def _parse_aseg_volumes(stats_file: Path) -> dict[str, float]:
    """Read aseg+DKT.stats and return {structure_name: volume_mm3}.

    Returns an empty dict if the file is missing or unreadable. Comment
    lines (#-prefixed) and rows with fewer than 5 whitespace-separated
    fields are ignored.
    """
    if not stats_file.exists():
        return {}
    volumes: dict[str, float] = {}
    for line in stats_file.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            volume = float(parts[3])
        except ValueError:
            continue
        volumes[parts[4]] = volume
    return volumes


def _check_structural_completeness(
    stats_file: Path,
) -> tuple[list[str], list[tuple[str, float]], list[tuple[str, float, float]]]:
    """Apply criteria 1-3 to aseg+DKT.stats.

    Criteria evaluated, in order:
      1. Required subcortical structure with volume == 0 → strict fail.
         Structures listed in REQUIRED_SUBCORTICAL_STRUCTURES.
      2. Required structure with 0 < volume < NOISE_FLOOR_MM3 (100 mm³)
         → fail. This is a noise-floor guard, not a validation against
         pediatric norms: a 9-year-old pallidum with normative range
         ~1500-2000 mm³ measured at < 100 mm³ is unambiguously a
         segmentation failure, not biological variability. Pediatric
         atlas integration (per-structure, age-stratified) is tracked
         as a v0.2+ TODO in docs/limitations.md.
      3. L/R asymmetry ratio > ASYMMETRY_MAX_RATIO (3:1) on paired
         structures → fail. This catches lateralized segmentation
         failures, NOT biological asymmetry. Pathological hippocampal
         asymmetry is typically 10-15% (Briellmann 1998, Bien 2005);
         a 3:1 ratio = 200% asymmetry is far beyond biological range
         and only fires on broken segmentations. If either side is 0
         the pair is skipped here (already handled by criterion 1).

    Returns three lists: (zero_volumes, below_noise_floor, extreme_asymmetry).
    Empty lists if the stats file is missing or all checks pass.
    """
    volumes = _parse_aseg_volumes(stats_file)
    if not volumes:
        logger.debug("QC: aseg+DKT.stats absent at %s — skipping structural checks", stats_file)
        return [], [], []

    zero_volumes: list[str] = []
    below_floor: list[tuple[str, float]] = []
    for name in REQUIRED_SUBCORTICAL_STRUCTURES:
        v = volumes.get(name, 0.0)
        if v == 0.0:
            zero_volumes.append(name)
        elif v < NOISE_FLOOR_MM3:
            below_floor.append((name, v))

    extreme_asymmetry: list[tuple[str, float, float]] = []
    for left_name, right_name in _PAIRED_SUBCORTICAL:
        left = volumes.get(left_name, 0.0)
        right = volumes.get(right_name, 0.0)
        # Guard: if either side is 0, criterion 1 already caught it.
        if left == 0.0 or right == 0.0:
            continue
        ratio = max(left, right) / min(left, right)
        if ratio > ASYMMETRY_MAX_RATIO:
            extreme_asymmetry.append((f"{left_name} vs {right_name}", left, right))

    return zero_volumes, below_floor, extreme_asymmetry


def _check_segmentation_qc(
    fastsurfer_output_dir: Path,
    subject_id: str,
) -> SegmentationQCFailure | None:
    """Run all QC criteria on a FastSurfer subject directory.

    Returns a structured failure if any of the following triggers fires:
      * "Total segmentation volume is too small" / "may be corrupted" warning
      * "None of the labels [...]" for any critical merged label
        (10001 deep subcortical, 10003 ventricles)
      * required subcortical structure with volume == 0  (criterion 1)
      * required structure below the 100 mm³ noise floor   (criterion 2)
      * L/R ratio > 3:1 on a paired subcortical structure  (criterion 3)

    Returns None when nothing fires, or when neither the log nor the
    stats file exists (caller handles those higher-level errors).
    """
    log_path = fastsurfer_output_dir / subject_id / "scripts" / "deep-seg.log"

    excerpts: list[str] = []
    missing_ids: set[int] = set()

    if log_path.exists():
        text = log_path.read_text(encoding="utf-8", errors="replace")

        seen: set[str] = set()
        for pat in _QC_WARNING_PATTERNS:
            for m in pat.finditer(text):
                line_start = text.rfind("\n", 0, m.start()) + 1
                line_end = text.find("\n", m.end())
                line = text[line_start:line_end if line_end != -1 else len(text)].strip()
                if line not in seen:
                    seen.add(line)
                    excerpts.append(line)

        for m in _QC_NONE_OF_LABELS_RE.finditer(text):
            merged = int(m.group(2))
            if merged in _QC_CRITICAL_MERGED_LABELS:
                ids = [int(x) for x in m.group(1).replace(" ", "").split(",") if x]
                missing_ids.update(ids)
    else:
        logger.debug("QC: deep-seg.log absent at %s — skipping log-based check", log_path)

    stats_file = fastsurfer_output_dir / subject_id / "stats" / "aseg+DKT.stats"
    zero_vol, low_vol, asym = _check_structural_completeness(stats_file)

    if excerpts or missing_ids or zero_vol or low_vol or asym:
        return SegmentationQCFailure(
            log_path=log_path,
            warning_excerpts=excerpts,
            missing_label_ids=missing_ids,
            zero_volume_structures=zero_vol,
            below_noise_floor=low_vol,
            extreme_asymmetry=asym,
        )
    return None

# Mapping SegId -> (hemisphere, region_name) pour les labels corticaux DKT
# ctx-lh-* = 1000+, ctx-rh-* = 2000+
DKT_CORTICAL_IDS: dict[int, tuple[str, str]] = {}
_DKT_REGIONS = [
    (2, "caudalanteriorcingulate"), (3, "caudalmiddlefrontal"),
    (5, "cuneus"), (6, "entorhinal"), (7, "fusiform"),
    (8, "inferiorparietal"), (9, "inferiortemporal"),
    (10, "isthmuscingulate"), (11, "lateraloccipital"),
    (12, "lateralorbitofrontal"), (13, "lingual"),
    (14, "medialorbitofrontal"), (15, "middletemporal"),
    (16, "parahippocampal"), (17, "paracentral"),
    (18, "parsopercularis"), (19, "parsorbitalis"),
    (20, "parstriangularis"), (21, "pericalcarine"),
    (22, "postcentral"), (23, "posteriorcingulate"),
    (24, "precentral"), (25, "precuneus"),
    (26, "rostralanteriorcingulate"), (27, "rostralmiddlefrontal"),
    (28, "superiorfrontal"), (29, "superiorparietal"),
    (30, "superiortemporal"), (31, "supramarginal"),
    (34, "transversetemporal"), (35, "insula"),
]
for _offset, _name in _DKT_REGIONS:
    DKT_CORTICAL_IDS[1000 + _offset] = ("lh", _name)
    DKT_CORTICAL_IDS[2000 + _offset] = ("rh", _name)

LOBE_REGIONS: dict[str, list[str]] = {
    "Frontal": [
        "superiorfrontal", "rostralmiddlefrontal", "caudalmiddlefrontal",
        "parsopercularis", "parstriangularis", "parsorbitalis",
        "lateralorbitofrontal", "medialorbitofrontal", "precentral",
        "frontalpole", "paracentral",
    ],
    "Parietal": [
        "superiorparietal", "inferiorparietal", "supramarginal",
        "postcentral", "precuneus",
    ],
    "Temporal": [
        "superiortemporal", "middletemporal", "inferiortemporal",
        "bankssts", "fusiform", "transversetemporal", "entorhinal",
        "temporalpole", "parahippocampal",
    ],
    "Occipital": [
        "lateraloccipital", "lingual", "cuneus", "pericalcarine",
    ],
    "Cingulate": [
        "rostralanteriorcingulate", "caudalanteriorcingulate",
        "posteriorcingulate", "isthmuscingulate",
    ],
    "Insula": [
        "insula",
    ],
}

# Approximate pediatric volume norms per lobe (cm³, per hemisphere mean ± SD).
# Source: aggregated literature for children 2–4 years old. These values are
# indicative — there is no universal standardized pediatric atlas. Override
# with case-appropriate norms when known.
PEDIATRIC_NORMS_VOLUME_CM3: dict[str, tuple[float, float]] = {
    "Frontal": (45.0, 6.0),
    "Parietal": (30.0, 4.0),
    "Temporal": (35.0, 5.0),
    "Occipital": (18.0, 3.0),
    "Cingulate": (8.0, 1.5),
    "Insula": (6.0, 1.0),
}

PEDIATRIC_NORMS_THICKNESS_MM: dict[str, tuple[float, float]] = {
    "Frontal": (3.2, 0.4),
    "Parietal": (2.8, 0.3),
    "Temporal": (3.1, 0.4),
    "Occipital": (2.4, 0.3),
    "Cingulate": (3.0, 0.4),
    "Insula": (3.5, 0.4),
}


@dataclass
class RegionStats:
    name: str
    hemisphere: str
    thickness_mm: float = 0.0
    surface_area_mm2: float = 0.0
    volume_mm3: float = 0.0
    num_vertices: int = 0


@dataclass
class SubcorticalStats:
    name: str
    volume_mm3: float = 0.0
    mean_intensity: float = 0.0


@dataclass
class QuantifyResult:
    cortical_regions: list[RegionStats] = field(default_factory=list)
    subcortical: list[SubcorticalStats] = field(default_factory=list)
    total_brain_volume_mm3: float = 0.0
    total_cortical_gm_volume_mm3: float = 0.0
    total_wm_volume_mm3: float = 0.0
    intracranial_volume_mm3: float = 0.0
    supratentorial_volume_mm3: float = 0.0
    has_thickness: bool = False
    lgi_available: bool = False
    lgi_regions: list[RegionStats] = field(default_factory=list)
    fastsurfer_log: str = ""


def find_t1_nifti(nifti_dir: Path) -> Path | None:
    candidates = sorted(nifti_dir.glob("t1_3d*.nii.gz"))
    if not candidates:
        return None
    for c in candidates:
        if "_real" not in c.stem:
            return c
    return candidates[0]


def check_docker() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def pull_fastsurfer_image() -> bool:
    try:
        result = subprocess.run(
            ["docker", "images", "-q", "deepmi/fastsurfer:latest"],
            capture_output=True, text=True, timeout=15,
        )
        if result.stdout.strip():
            logger.info("Image deepmi/fastsurfer:latest already present")
            return True

        logger.info("Pulling image deepmi/fastsurfer:latest...")
        result = subprocess.run(
            ["docker", "pull", "deepmi/fastsurfer:latest"],
            capture_output=True, text=True, timeout=600,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _convert_win_path_to_docker(path: Path) -> str:
    resolved = path.resolve()
    posix = resolved.as_posix()
    if len(posix) >= 2 and posix[1] == ":":
        drive = posix[0].lower()
        return f"/{drive}{posix[2:]}"
    return posix


def run_fastsurfer(
    t1_path: Path,
    output_dir: Path,
    subject_id: str = "subject",
    threads: int = 8,
    timeout_minutes: int = 180,
    fs_license: Path | None = None,
    surf_only: bool = False,
) -> tuple[bool, str]:
    """Run FastSurfer via Docker on the T1 NIfTI. Returns (success, log_output)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    input_dir = t1_path.parent.resolve()
    output_resolved = output_dir.resolve()
    t1_filename = t1_path.name

    input_mount = _convert_win_path_to_docker(input_dir)
    output_mount = _convert_win_path_to_docker(output_resolved)

    base_docker = [
        "docker", "run", "--rm",
        "--user", "root",
        "--memory", "24g",
        "--memory-swap", "28g",
        "-v", f"{input_mount}:/data/input:ro",
        "-v", f"{output_mount}:/data/output",
    ]

    if fs_license and fs_license.exists():
        license_mount = _convert_win_path_to_docker(fs_license.parent)
        base_docker.extend(["-v", f"{license_mount}:/license:ro"])

    combined_log = ""

    if not surf_only:
        seg_cmd = base_docker + [
            "deepmi/fastsurfer:latest",
            "--t1", f"/data/input/{t1_filename}",
            "--sid", subject_id,
            "--sd", "/data/output",
            "--threads", str(threads),
            "--allow_root",
            "--seg_only",
        ]

        logger.info("Launching FastSurfer (segmentation)...")
        logger.debug("Command: %s", " ".join(seg_cmd))

        try:
            result = subprocess.run(
                seg_cmd,
                capture_output=True, timeout=timeout_minutes * 60,
                encoding="utf-8", errors="replace",
            )
            combined_log += f"=== SEGMENTATION (seg_only) ===\n{result.stdout}\n{result.stderr}\n"

            if result.returncode != 0:
                logger.error("FastSurfer segmentation failed (code %d)", result.returncode)
                logger.error("stderr: %s", result.stderr[-2000:] if result.stderr else "")
                return False, combined_log
        except subprocess.TimeoutExpired:
            logger.error("FastSurfer segmentation timeout (%d min)", timeout_minutes)
            return False, combined_log + "\nTIMEOUT during segmentation\n"
    else:
        logger.info("Segmentation skipped (--surf-only)")
        combined_log += "=== SEGMENTATION SKIPPED (--surf-only) ===\n"

    if fs_license and fs_license.exists():
        logger.info("Launching FastSurfer (surfaces)...")
        license_name = fs_license.name

        surf_cmd = base_docker + [
            "deepmi/fastsurfer:latest",
            "--t1", f"/data/input/{t1_filename}",
            "--sid", subject_id,
            "--sd", "/data/output",
            "--threads", str(threads),
            "--allow_root",
            "--fs_license", f"/license/{license_name}",
            "--surf_only",
        ]

        try:
            result = subprocess.run(
                surf_cmd,
                capture_output=True, timeout=timeout_minutes * 60,
                encoding="utf-8", errors="replace",
            )
            combined_log += f"\n=== SURFACES (surf_only) ===\n{result.stdout}\n{result.stderr}\n"

            if result.returncode != 0:
                logger.warning("FastSurfer surfaces failed (code %d) — partial report", result.returncode)
                logger.warning("stderr: %s", result.stderr[-2000:] if result.stderr else "")
        except subprocess.TimeoutExpired:
            logger.warning("FastSurfer surfaces timeout — partial report")
            combined_log += "\nTIMEOUT during surface reconstruction\n"
    else:
        logger.info("Surface pass skipped (no FreeSurfer license)")
        logger.info("To obtain cortical thickness and LGI, provide --fs-license")
        combined_log += "\n=== SURFACES SKIPPED (no FreeSurfer license) ===\n"

    return True, combined_log


def parse_aseg_dkt_stats(stats_file: Path) -> tuple[list[RegionStats], list[SubcorticalStats], dict[str, float]]:
    cortical = []
    subcortical = []
    globals_dict: dict[str, float] = {}

    if not stats_file.exists():
        logger.warning("aseg+DKT.stats file not found: %s", stats_file)
        return cortical, subcortical, globals_dict

    content = stats_file.read_text(encoding="utf-8", errors="replace")

    for line in content.splitlines():
        match = re.match(r"# Measure\s+(\S+),\s+\S+,\s+[^,]+,\s+([\d.]+),\s+mm\^3", line)
        if match:
            globals_dict[match.group(1)] = float(match.group(2))

    in_table = False
    for line in content.splitlines():
        if line.startswith("# ColHeaders"):
            in_table = True
            continue
        if not in_table or line.startswith("#"):
            continue

        parts = line.split()
        if len(parts) < 6:
            continue

        seg_id = int(parts[1])
        volume = float(parts[3])
        struct_name = parts[4]
        mean_intensity = float(parts[5]) if len(parts) > 5 else 0.0

        if seg_id in DKT_CORTICAL_IDS:
            hemi, region_name = DKT_CORTICAL_IDS[seg_id]
            cortical.append(RegionStats(
                name=region_name,
                hemisphere=hemi,
                volume_mm3=volume,
            ))
        else:
            subcortical.append(SubcorticalStats(
                name=struct_name,
                volume_mm3=volume,
                mean_intensity=mean_intensity,
            ))

    return cortical, subcortical, globals_dict


def parse_aparc_stats(stats_file: Path, hemisphere: str) -> list[RegionStats]:
    regions = []
    if not stats_file.exists():
        return regions

    in_table = False
    for line in stats_file.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("# ColHeaders"):
            in_table = True
            continue
        if in_table and not line.startswith("#"):
            parts = line.split()
            if len(parts) >= 10:
                regions.append(RegionStats(
                    name=parts[0],
                    hemisphere=hemisphere,
                    num_vertices=int(parts[1]),
                    surface_area_mm2=float(parts[2]),
                    volume_mm3=float(parts[3]),
                    thickness_mm=float(parts[4]),
                ))
    return regions


def _region_to_lobe(region_name: str) -> str:
    clean = region_name.lower().replace("-", "").replace("_", "")
    for lobe, regions in LOBE_REGIONS.items():
        for r in regions:
            if r.lower() == clean:
                return lobe
    return "Other"


def _compute_z_score_thickness(value: float, lobe: str) -> float | None:
    if lobe not in PEDIATRIC_NORMS_THICKNESS_MM:
        return None
    mean, sd = PEDIATRIC_NORMS_THICKNESS_MM[lobe]
    if sd == 0:
        return None
    return (value - mean) / sd


def _compute_z_score_volume(value_cm3: float, lobe: str) -> float | None:
    if lobe not in PEDIATRIC_NORMS_VOLUME_CM3:
        return None
    mean, sd = PEDIATRIC_NORMS_VOLUME_CM3[lobe]
    if sd == 0:
        return None
    return (value_cm3 - mean) / sd


def _resolve_surface_path(surf_dir: Path, name: str) -> Path | None:
    direct = surf_dir / name
    try:
        if direct.exists() and direct.stat().st_size > 0:
            return direct
    except OSError:
        pass
    fallback = surf_dir / f"{name}.T1"
    if fallback.exists():
        return fallback
    return None


def _compute_face_areas(vertices, faces):
    import numpy as np
    v0 = vertices[faces[:, 0]]
    v1 = vertices[faces[:, 1]]
    v2 = vertices[faces[:, 2]]
    cross = np.cross(v1 - v0, v2 - v0)
    return 0.5 * np.linalg.norm(cross, axis=1)


def _vertex_areas(vertices, faces):
    import numpy as np
    face_areas = _compute_face_areas(vertices, faces)
    vert_areas = np.zeros(len(vertices))
    for i in range(3):
        np.add.at(vert_areas, faces[:, i], face_areas / 3.0)
    return vert_areas


def compute_lgi_from_surfaces(
    surf_dir: Path,
    label_dir: Path,
) -> list[RegionStats]:
    """Compute regional Gyrification Index from pial and white surfaces.

    Method: ratio of pial / white surface area per DKT region. Both surfaces
    share the same topology (vertices and faces), only positions differ.

    - Normal brain: ratio ~1.4-1.8 (pial larger thanks to sulci).
    - Reduced gyrification (e.g. pachygyria): ~1.0-1.2.
    - Increased gyrification (e.g. polymicrogyria): > 2.0.

    Returns RegionStats with thickness_mm = LGI ratio for the region.
    """
    try:
        import nibabel as nib
        import numpy as np
    except ImportError as e:
        logger.warning("LGI dependencies missing (%s) — pip install nibabel", e)
        return []

    results: list[RegionStats] = []

    for hemi in ["lh", "rh"]:
        pial_path = _resolve_surface_path(surf_dir, f"{hemi}.pial")
        white_path = _resolve_surface_path(surf_dir, f"{hemi}.white")
        if not pial_path:
            logger.warning("%s.pial surface not found", hemi)
            continue
        if not white_path:
            logger.warning("%s.white surface not found", hemi)
            continue

        annot_path = label_dir / f"{hemi}.aparc.DKTatlas.mapped.annot"
        if not annot_path.exists():
            annot_path = label_dir / f"{hemi}.aparc.DKTatlas.annot"
        if not annot_path.exists():
            logger.warning("DKT annotation not found for %s", hemi)
            continue

        logger.info("Computing LGI for %s (pial/white ratio)", hemi)

        pial_verts, pial_faces = nib.freesurfer.read_geometry(str(pial_path))
        white_verts, white_faces = nib.freesurfer.read_geometry(str(white_path))
        labels, ctab, names = nib.freesurfer.read_annot(str(annot_path))

        region_names = [n.decode() if isinstance(n, bytes) else n for n in names]

        pial_vert_areas = _vertex_areas(pial_verts, pial_faces)
        white_vert_areas = _vertex_areas(white_verts, white_faces)

        unique_labels = np.unique(labels)
        for lab_idx in unique_labels:
            if lab_idx < 0 or lab_idx >= len(region_names):
                continue
            rname = region_names[lab_idx]
            if rname in ("unknown", "corpuscallosum", "Unknown", "???"):
                continue

            mask = labels == lab_idx
            if mask.sum() < 10:
                continue

            region_pial_area = pial_vert_areas[mask].sum()
            region_white_area = white_vert_areas[mask].sum()

            if region_white_area > 0:
                lgi = region_pial_area / region_white_area
            else:
                lgi = 1.0

            results.append(RegionStats(
                name=rname,
                hemisphere=hemi,
                thickness_mm=lgi,
                surface_area_mm2=region_pial_area,
                volume_mm3=0.0,
            ))

        logger.info("LGI %s: %d regions computed", hemi, sum(1 for r in results if r.hemisphere == hemi))

    return results


def extract_results(fastsurfer_output_dir: Path, subject_id: str = "subject") -> QuantifyResult:
    """Extract all quantitative results from FastSurfer output."""
    subj_dir = fastsurfer_output_dir / subject_id
    stats_dir = subj_dir / "stats"
    result = QuantifyResult()

    lh_aparc = stats_dir / "lh.aparc.DKTatlas.mapped.stats"
    rh_aparc = stats_dir / "rh.aparc.DKTatlas.mapped.stats"
    if not lh_aparc.exists():
        lh_aparc = stats_dir / "lh.aparc.stats"
    if not rh_aparc.exists():
        rh_aparc = stats_dir / "rh.aparc.stats"

    if lh_aparc.exists() and rh_aparc.exists():
        result.has_thickness = True
        result.cortical_regions.extend(parse_aparc_stats(lh_aparc, "lh"))
        result.cortical_regions.extend(parse_aparc_stats(rh_aparc, "rh"))

    aseg_dkt = stats_dir / "aseg+DKT.stats"
    cortical_vol, subcortical, globals_dict = parse_aseg_dkt_stats(aseg_dkt)

    if not result.has_thickness and cortical_vol:
        result.cortical_regions = cortical_vol

    result.subcortical = subcortical

    aseg_classic = stats_dir / "aseg.stats"
    if aseg_classic.exists():
        _, _, classic_globals = parse_aseg_dkt_stats(aseg_classic)
        globals_dict.update(classic_globals)

    result.total_brain_volume_mm3 = globals_dict.get("BrainSeg", globals_dict.get("BrainSegVol", 0.0))
    result.total_wm_volume_mm3 = globals_dict.get("CerebralWhiteMatter", globals_dict.get("CerebralWhiteMatterVol", 0.0))
    result.intracranial_volume_mm3 = globals_dict.get("Mask", globals_dict.get("EstimatedTotalIntraCranialVol", 0.0))
    result.supratentorial_volume_mm3 = globals_dict.get("SupraTentorial", globals_dict.get("SupraTentorialVol", 0.0))

    total_ctx = sum(r.volume_mm3 for r in result.cortical_regions)
    result.total_cortical_gm_volume_mm3 = total_ctx

    for hemi in ["lh", "rh"]:
        lgi_file = stats_dir / f"{hemi}.aparc.pial_lgi.stats"
        if lgi_file.exists():
            result.lgi_available = True
            result.lgi_regions.extend(parse_aparc_stats(lgi_file, hemi))

    if not result.lgi_available:
        surf_dir = subj_dir / "surf"
        label_dir = subj_dir / "label"
        lgi_regions = compute_lgi_from_surfaces(surf_dir, label_dir)
        if lgi_regions:
            result.lgi_available = True
            result.lgi_regions = lgi_regions

    return result


def _format_subject_header(context: dict | None) -> list[str]:
    """Return the subject metadata block at the top of the report.

    Only renders fields present in ``context.patient_context`` (free-form).
    No PHI is hardcoded anywhere — when no context is provided, only the
    generation date is shown.
    """
    lines = []
    context = context or {}
    pc = (context.get("patient_context") or "").strip()
    if pc:
        lines.append("**Provided context**:")
        lines.append("")
        for ln in pc.splitlines():
            lines.append(f"> {ln}")
        lines.append("")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"**Report generated**: {now}")
    lines.append("**Tool**: FastSurfer v2.4 (deepmi/fastsurfer:latest)")
    lines.append("")
    return lines


def generate_quantitative_report(
    result: QuantifyResult,
    output_path: Path,
    context: dict | None = None,
) -> Path:
    """Generate the quantitative analysis report in Markdown.

    Args:
        result: parsed FastSurfer output.
        output_path: where to write the .md file.
        context: optional dict (see ``config.load_patient_context``). May
            contain ``patient_context`` (anonymized free-form clinical
            block) and ``clinical_correlation.quantitative_criteria`` —
            a list of dicts ``{label, expected, threshold, side}`` used
            to render an optional "concordance" subsection. Without a
            context, only objective measurements are reported.
    """
    lines: list[str] = []
    lobe_order = ["Frontal", "Parietal", "Temporal", "Occipital", "Cingulate", "Insula"]

    lines.append("# Quantitative analysis report — Brain MRI")
    lines.append("")
    lines.append(as_markdown_blockquote())
    lines.append("")
    lines.extend(_format_subject_header(context))

    lines.append("> **Warning:** FastSurfer is primarily validated on adult brains. "
                 "In young children, myelination may be incomplete and the gray-white "
                 "contrast may differ from adults, which can affect segmentation "
                 "accuracy. Z-scores use approximate pediatric norms from the "
                 "literature, not a standardized atlas.")
    lines.append("")

    # === 1. Global volumetry ===
    lines.append("## 1. Global volumetry")
    lines.append("")
    lines.append("| Measurement | Volume (cm³) |")
    lines.append("|--------|-------------|")
    lines.append(f"| Intracranial mask volume | {result.intracranial_volume_mm3 / 1000:.1f} |")
    lines.append(f"| Total brain volume (BrainSeg) | {result.total_brain_volume_mm3 / 1000:.1f} |")
    lines.append(f"| Supratentorial volume | {result.supratentorial_volume_mm3 / 1000:.1f} |")
    lines.append(f"| Cortical gray matter (sum of regions) | {result.total_cortical_gm_volume_mm3 / 1000:.1f} |")
    lines.append(f"| Cerebral white matter | {result.total_wm_volume_mm3 / 1000:.1f} |")
    lines.append("")

    lobe_data: dict[str, dict[str, list[float]]] = {}
    for region in result.cortical_regions:
        lobe = _region_to_lobe(region.name)
        if lobe == "Other":
            continue
        if lobe not in lobe_data:
            lobe_data[lobe] = {"lh": [], "rh": []}
        if result.has_thickness:
            lobe_data[lobe][region.hemisphere].append(region.thickness_mm)
        else:
            lobe_data[lobe][region.hemisphere].append(region.volume_mm3)

    # === 2. Cortical data by lobe ===
    if result.has_thickness:
        lines.append("## 2. Cortical thickness by lobe")
        lines.append("")
        lines.append("| Lobe | Left (mm) | Right (mm) | Asymmetry (R-L) | Z-score L | Z-score R | Interpretation |")
        lines.append("|------|------------|------------|----------------|-----------|-----------|----------------|")

        for lobe in lobe_order:
            if lobe not in lobe_data:
                continue
            lh_vals = lobe_data[lobe].get("lh", [])
            rh_vals = lobe_data[lobe].get("rh", [])
            lh_mean = sum(lh_vals) / len(lh_vals) if lh_vals else 0
            rh_mean = sum(rh_vals) / len(rh_vals) if rh_vals else 0
            asym = rh_mean - lh_mean

            z_lh = _compute_z_score_thickness(lh_mean, lobe)
            z_rh = _compute_z_score_thickness(rh_mean, lobe)
            z_lh_str = f"{z_lh:+.1f}" if z_lh is not None else "—"
            z_rh_str = f"{z_rh:+.1f}" if z_rh is not None else "—"

            interp_parts = []
            if z_rh is not None and z_rh > 2.0:
                interp_parts.append("**THICKENED R**")
            if z_lh is not None and z_lh > 2.0:
                interp_parts.append("**THICKENED L**")
            if abs(asym) > 0.3:
                side = "R > L" if asym > 0 else "L > R"
                interp_parts.append(f"Asymmetry {side}")
            if not interp_parts:
                interp_parts.append("Normal")

            lines.append(
                f"| {lobe} | {lh_mean:.2f} | {rh_mean:.2f} | {asym:+.2f} "
                f"| {z_lh_str} | {z_rh_str} | {', '.join(interp_parts)} |"
            )
    else:
        lines.append("## 2. Cortical volumes by lobe")
        lines.append("")
        lines.append("> **Note:** Cortical thickness is not available (requires the surface pass "
                     "with FreeSurfer license). Regional volumes below allow assessment of "
                     "cortical hypertrophy by lobe.")
        lines.append("")
        lines.append("| Lobe | Left (cm³) | Right (cm³) | Total (cm³) | Asymmetry R-L (cm³) | Z-score L | Z-score R | Interpretation |")
        lines.append("|------|-------------|-------------|------------|---------------------|-----------|-----------|----------------|")

        for lobe in lobe_order:
            if lobe not in lobe_data:
                continue
            lh_vals = lobe_data[lobe].get("lh", [])
            rh_vals = lobe_data[lobe].get("rh", [])
            lh_sum = sum(lh_vals) / 1000
            rh_sum = sum(rh_vals) / 1000
            total = lh_sum + rh_sum
            asym = rh_sum - lh_sum

            z_lh = _compute_z_score_volume(lh_sum, lobe)
            z_rh = _compute_z_score_volume(rh_sum, lobe)
            z_lh_str = f"{z_lh:+.1f}" if z_lh is not None else "—"
            z_rh_str = f"{z_rh:+.1f}" if z_rh is not None else "—"

            interp_parts = []
            if z_rh is not None and z_rh > 2.0:
                interp_parts.append("**HIGH VOLUME R**")
            if z_lh is not None and z_lh > 2.0:
                interp_parts.append("**HIGH VOLUME L**")
            if z_rh is not None and z_rh < -2.0:
                interp_parts.append("Reduced volume R")
            if z_lh is not None and z_lh < -2.0:
                interp_parts.append("Reduced volume L")
            if abs(asym) > 2.0:
                side = "R > L" if asym > 0 else "L > R"
                interp_parts.append(f"Asymmetry {side}")
            if not interp_parts:
                interp_parts.append("Normal")

            lines.append(
                f"| {lobe} | {lh_sum:.1f} | {rh_sum:.1f} | {total:.1f} | {asym:+.1f} "
                f"| {z_lh_str} | {z_rh_str} | {', '.join(interp_parts)} |"
            )

    lines.append("")

    # === 3. Region detail ===
    if result.has_thickness:
        lines.append("## 3. Cortical thickness — region detail")
        lines.append("")
        lines.append("### Regions with abnormal thickness (Z > 2.0)")
    else:
        lines.append("## 3. Cortical volumes — region detail")
        lines.append("")
        lines.append("### Regions with notable volume")

    lines.append("")

    lines.append("<details>")
    lines.append("<summary>Click to expand all regions</summary>")
    lines.append("")

    if result.has_thickness:
        lines.append("| Region | H. | Lobe | Thickness (mm) | Z-score | Surface area (mm²) | Volume (mm³) |")
        lines.append("|--------|---|------|---------------|---------|---------------|-------------|")
        for region in sorted(result.cortical_regions, key=lambda r: (r.hemisphere, r.name)):
            lobe = _region_to_lobe(region.name)
            z = _compute_z_score_thickness(region.thickness_mm, lobe)
            z_str = f"{z:+.1f}" if z is not None else "—"
            h = "L" if region.hemisphere == "lh" else "R"
            marker = " **" if z is not None and z > 2.0 else ""
            lines.append(
                f"| {marker}{region.name}{marker} | {h} | {lobe} "
                f"| {region.thickness_mm:.2f} | {z_str} "
                f"| {region.surface_area_mm2:.0f} | {region.volume_mm3:.0f} |"
            )
    else:
        lines.append("| Region | H. | Lobe | Volume (cm³) |")
        lines.append("|--------|---|------|-------------|")
        for region in sorted(result.cortical_regions, key=lambda r: (-r.volume_mm3,)):
            lobe = _region_to_lobe(region.name)
            h = "L" if region.hemisphere == "lh" else "R"
            lines.append(
                f"| {region.name} | {h} | {lobe} | {region.volume_mm3 / 1000:.2f} |"
            )

    lines.append("")
    lines.append("</details>")
    lines.append("")

    # === 4. Subcortical volumetry ===
    lines.append("## 4. Subcortical volumetry")
    lines.append("")
    if result.subcortical:
        key_patterns = [
            "thalamus", "caudate", "putamen", "pallidum",
            "hippocampus", "amygdala", "cerebellum", "ventricle",
            "brain-stem", "brainstem", "accumbens", "ventraldc",
        ]
        lines.append("| Structure | Volume (cm³) |")
        lines.append("|-----------|-------------|")
        for struct in result.subcortical:
            name_lower = struct.name.lower().replace("-", "").replace("_", "")
            if any(k.replace("-", "") in name_lower for k in key_patterns) or struct.volume_mm3 > 1000:
                lines.append(f"| {struct.name} | {struct.volume_mm3 / 1000:.2f} |")

        lh_hippo = next((s.volume_mm3 for s in result.subcortical if "Left-Hippocampus" in s.name), None)
        rh_hippo = next((s.volume_mm3 for s in result.subcortical if "Right-Hippocampus" in s.name), None)
        if lh_hippo is not None and rh_hippo is not None:
            asym_pct = (rh_hippo - lh_hippo) / ((lh_hippo + rh_hippo) / 2) * 100
            lines.append("")
            lines.append(f"**Hippocampal asymmetry**: {asym_pct:+.1f}% "
                        f"({'R > L' if asym_pct > 0 else 'L > R'}) — "
                        f"{'normal (< 10%)' if abs(asym_pct) < 10 else '**notable (≥ 10%)**'}")
    else:
        lines.append("*Subcortical data not available.*")
    lines.append("")

    # === 5. LGI ===
    lines.append("## 5. Local gyrification index (LGI)")
    lines.append("")
    if result.lgi_available and result.lgi_regions:
        lines.append("> **Method:** regional LGI = pial surface area / white surface area "
                     "per DKT parcellation. Normal brain ~1.4-1.8, reduced gyrification "
                     "(e.g. pachygyria) ~1.0-1.2, increased gyrification (e.g. polymicrogyria) > 2.0.")
        lines.append("")
        lines.append("| Lobe | LGI Left | LGI Right | Interpretation |")
        lines.append("|------|-----------|-----------|----------------|")

        lgi_by_lobe: dict[str, dict[str, list[float]]] = {}
        for region in result.lgi_regions:
            lobe = _region_to_lobe(region.name)
            if lobe not in lgi_by_lobe:
                lgi_by_lobe[lobe] = {"lh": [], "rh": []}
            lgi_by_lobe[lobe][region.hemisphere].append(region.thickness_mm)

        for lobe in lobe_order:
            if lobe not in lgi_by_lobe:
                continue
            lh_vals = lgi_by_lobe[lobe].get("lh", [])
            rh_vals = lgi_by_lobe[lobe].get("rh", [])
            lh_mean = sum(lh_vals) / len(lh_vals) if lh_vals else 0
            rh_mean = sum(rh_vals) / len(rh_vals) if rh_vals else 0

            if lh_mean < 1.15 or rh_mean < 1.15:
                interp = "**Severely reduced gyrification**"
            elif lh_mean < 1.3 or rh_mean < 1.3:
                interp = "**Reduced gyrification**"
            elif lh_mean < 1.4 or rh_mean < 1.4:
                interp = "Borderline low gyrification"
            else:
                interp = "Normal"

            lines.append(f"| {lobe} | {lh_mean:.2f} | {rh_mean:.2f} | {interp} |")
    else:
        lines.append("*LGI not available. LGI computation requires complete surface "
                     "reconstruction (`--surf_only` pass with FreeSurfer license).*")
        lines.append("")
        lines.append("1. Obtain a free FreeSurfer license: https://surfer.nmr.mgh.harvard.edu/registration.html")
        lines.append("2. Re-run: `neuro-analyzer quantify <nifti_dir> --fs-license /path/to/license.txt`")
    lines.append("")

    # === 6. Limitations ===
    lines.append("## 6. Important limitations")
    lines.append("")
    lines.append("1. **Pediatric brain validation**: FastSurfer is primarily validated on "
                 "adult brains. In children, incomplete myelination and atypical gray-white "
                 "contrast can affect segmentation accuracy.")
    lines.append("2. **Cortical malformations**: Any malformation of cortical development "
                 "can disrupt segmentation algorithms that expect normal sulcal anatomy. "
                 "Volumes of affected regions may be under- or overestimated.")
    lines.append("3. **Pediatric norms**: Z-scores are approximations based on the "
                 "literature. There is no universal standardized norm for this age range.")
    if not result.has_thickness:
        lines.append("4. **Volumetric data only**: Without the surface pass (requires a "
                     "free FreeSurfer license), cortical thickness and LGI are not "
                     "available. Volumes are an indirect proxy for thickness.")
    lines.append("5. **Validation required**: These quantitative results must be correlated "
                 "with qualitative visual interpretation by an experienced neuroradiologist.")
    lines.append("")
    lines.append("---")
    lines.append("*Report automatically generated by neuro-analyzer. Research / educational "
                 "tool — does not constitute a medical diagnosis.*")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Quantitative report saved: %s", output_path)
    return output_path
