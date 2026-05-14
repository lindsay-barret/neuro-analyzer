"""Smart selection of the most informative slices."""

import logging
from dataclasses import dataclass

import nibabel as nib

from .config import SLICE_COUNTS, FRONTAL_FOCUS_RANGE, FOCAL_DENSITY_RATIO

logger = logging.getLogger(__name__)


@dataclass
class SliceSelection:
    """A slice selected for analysis."""
    slice_index: int
    plane: str  # axial, coronal, sagittal
    sequence: str  # t1, swi, etc.
    position_fraction: float  # 0.0 = inf/ant/left, 1.0 = sup/post/right
    is_focal: bool  # In the main region of interest
    anatomical_level: str  # Anatomical level description


def _estimate_anatomical_level_axial(fraction: float) -> str:
    """Estimate the anatomical level of an axial slice based on its position."""
    if fraction < 0.15:
        return "inferior cerebellum / brainstem"
    elif fraction < 0.25:
        return "upper cerebellum / temporal poles"
    elif fraction < 0.35:
        return "basal ganglia level"
    elif fraction < 0.45:
        return "lateral ventricles (body)"
    elif fraction < 0.55:
        return "corona radiata / centrum semiovale (inferior)"
    elif fraction < 0.65:
        return "centrum semiovale (mid)"
    elif fraction < 0.75:
        return "centrum semiovale (superior) / high convexity"
    elif fraction < 0.85:
        return "high convexity / parasagittal cortex"
    else:
        return "vertex"


def _estimate_anatomical_level_coronal(fraction: float) -> str:
    """Estimate the anatomical level of a coronal slice."""
    if fraction < 0.15:
        return "frontal pole (anterior)"
    elif fraction < 0.25:
        return "prefrontal cortex"
    elif fraction < 0.35:
        return "anterior frontal / genu of corpus callosum"
    elif fraction < 0.45:
        return "mid frontal / anterior horn of lateral ventricles"
    elif fraction < 0.55:
        return "central sulcus region"
    elif fraction < 0.65:
        return "parietal lobe / body of lateral ventricles"
    elif fraction < 0.75:
        return "posterior parietal / trigone of lateral ventricles"
    elif fraction < 0.85:
        return "occipital lobe / splenium of corpus callosum"
    else:
        return "occipital pole (posterior)"


def _estimate_anatomical_level_sagittal(fraction: float) -> str:
    """Estimate the anatomical level of a sagittal slice."""
    if fraction < 0.35:
        return "right hemisphere (lateral)"
    elif fraction < 0.45:
        return "right hemisphere (parasagittal)"
    elif fraction < 0.55:
        return "midline (interhemispheric fissure / corpus callosum)"
    elif fraction < 0.65:
        return "left hemisphere (parasagittal)"
    else:
        return "left hemisphere (lateral)"


def select_slices_for_volume(
    nifti_path: str,
    sequence_type: str,
    max_slices: int | None = None,
) -> list[SliceSelection]:
    """
    Select the most informative slices of a NIfTI volume.

    For a 3D T1, slices are generated in all 3 planes.
    For a 2D SWI or T2, only axial slices are generated.

    Strategy: denser sampling in the frontal region (region of interest
    for pachygyria) and sparser elsewhere.
    """
    img = nib.load(str(nifti_path))
    data = img.get_fdata()
    shape = data.shape

    logger.info(f"Volume loaded: {nifti_path} — shape {shape}")

    selections = []

    if sequence_type.startswith("t1"):
        # T1 3D: generate in all 3 planes
        for plane, axis, count_key in [
            ("axial", 2, "t1_axial"),
            ("coronal", 1, "t1_coronal"),
            ("sagittal", 0, "t1_sagittal"),
        ]:
            n_total = SLICE_COUNTS.get(count_key, 10)
            if max_slices:
                n_total = min(n_total, max_slices // 3)

            dim_size = shape[axis]
            indices = _select_indices_with_focus(dim_size, n_total, FRONTAL_FOCUS_RANGE)

            for idx in indices:
                fraction = idx / (dim_size - 1)
                is_focal = FRONTAL_FOCUS_RANGE[0] <= fraction <= FRONTAL_FOCUS_RANGE[1]

                if plane == "axial":
                    level = _estimate_anatomical_level_axial(fraction)
                elif plane == "coronal":
                    level = _estimate_anatomical_level_coronal(fraction)
                else:
                    level = _estimate_anatomical_level_sagittal(fraction)

                selections.append(SliceSelection(
                    slice_index=idx,
                    plane=plane,
                    sequence=sequence_type,
                    position_fraction=fraction,
                    is_focal=is_focal,
                    anatomical_level=level,
                ))

    elif sequence_type.startswith("swi"):
        # SWI: axial slices only
        n_total = SLICE_COUNTS.get("swi_axial", 12)
        if max_slices:
            n_total = min(n_total, max_slices)

        dim_size = shape[2]  # axial = last axis
        indices = _select_indices_with_focus(dim_size, n_total, FRONTAL_FOCUS_RANGE)

        for idx in indices:
            fraction = idx / (dim_size - 1)
            selections.append(SliceSelection(
                slice_index=idx,
                plane="axial",
                sequence=sequence_type,
                position_fraction=fraction,
                is_focal=FRONTAL_FOCUS_RANGE[0] <= fraction <= FRONTAL_FOCUS_RANGE[1],
                anatomical_level=_estimate_anatomical_level_axial(fraction),
            ))

    else:
        # Other 2D sequences: axial slices
        n_total = 10
        if max_slices:
            n_total = min(n_total, max_slices)

        dim_size = shape[2]
        step = max(1, dim_size // n_total)
        indices = list(range(dim_size // 10, dim_size * 9 // 10, step))[:n_total]

        for idx in indices:
            fraction = idx / (dim_size - 1)
            selections.append(SliceSelection(
                slice_index=idx,
                plane="axial",
                sequence=sequence_type,
                position_fraction=fraction,
                is_focal=False,
                anatomical_level=_estimate_anatomical_level_axial(fraction),
            ))

    logger.info(f"  {len(selections)} slices selected for {sequence_type}")
    return selections


def _select_indices_with_focus(
    dim_size: int,
    n_total: int,
    focus_range: tuple[float, float],
) -> list[int]:
    """
    Select indices with higher density in the focal zone.

    The focal zone (frontal region for pachygyria) receives FOCAL_DENSITY_RATIO
    times more slices than the non-focal zones.
    """
    focus_start = int(focus_range[0] * dim_size)
    focus_end = int(focus_range[1] * dim_size)
    focus_size = focus_end - focus_start
    non_focus_size = dim_size - focus_size

    # Distribute slices according to density
    if non_focus_size > 0:
        ratio = FOCAL_DENSITY_RATIO
        n_focal = int(n_total * (focus_size * ratio) / (focus_size * ratio + non_focus_size))
        n_non_focal = n_total - n_focal
    else:
        n_focal = n_total
        n_non_focal = 0

    n_focal = max(n_focal, 1)

    indices = []

    # Indices inside the focal zone
    if n_focal > 1:
        step = focus_size / (n_focal + 1)
        indices.extend([int(focus_start + step * (i + 1)) for i in range(n_focal)])
    elif n_focal == 1:
        indices.append((focus_start + focus_end) // 2)

    # Indices outside the focal zone
    if n_non_focal > 0:
        # Before the focal zone
        n_before = n_non_focal // 2
        if n_before > 0 and focus_start > 0:
            step = focus_start / (n_before + 1)
            indices.extend([int(step * (i + 1)) for i in range(n_before)])

        # After the focal zone
        n_after = n_non_focal - n_before
        if n_after > 0 and focus_end < dim_size:
            remaining = dim_size - focus_end
            step = remaining / (n_after + 1)
            indices.extend([int(focus_end + step * (i + 1)) for i in range(n_after)])

    # Filter valid indices and sort
    indices = sorted(set(max(0, min(dim_size - 1, i)) for i in indices))
    return indices
