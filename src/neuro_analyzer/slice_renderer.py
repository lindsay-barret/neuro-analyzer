"""Render NIfTI slices to PNG images."""

import logging
from pathlib import Path

import numpy as np
import nibabel as nib
import matplotlib
matplotlib.use('Agg')  # Backend non-interactif
import matplotlib.pyplot as plt

from .config import PNG_DPI, PNG_SIZE_INCHES
from .slice_selector import SliceSelection

logger = logging.getLogger(__name__)


def _normalize_slice(slice_data: np.ndarray, percentile_low: float = 1, percentile_high: float = 99) -> np.ndarray:
    """Normalize a slice for display (automatic windowing)."""
    # Ignore zero voxels (background)
    nonzero = slice_data[slice_data > 0]
    if len(nonzero) == 0:
        return np.zeros_like(slice_data, dtype=np.float32)

    vmin = np.percentile(nonzero, percentile_low)
    vmax = np.percentile(nonzero, percentile_high)

    if vmax <= vmin:
        return np.zeros_like(slice_data, dtype=np.float32)

    normalized = (slice_data.astype(np.float32) - vmin) / (vmax - vmin)
    return np.clip(normalized, 0, 1)


def _extract_slice(data: np.ndarray, selection: SliceSelection) -> np.ndarray:
    """Extract a 2D slice from the 3D volume along the specified plane."""
    idx = selection.slice_index

    if selection.plane == "axial":
        # Axial slice: axes 0 and 1, index on axis 2
        if idx >= data.shape[2]:
            idx = data.shape[2] - 1
        slice_2d = data[:, :, idx]
    elif selection.plane == "coronal":
        # Coronal slice: axes 0 and 2, index on axis 1
        if idx >= data.shape[1]:
            idx = data.shape[1] - 1
        slice_2d = data[:, idx, :]
    elif selection.plane == "sagittal":
        # Sagittal slice: axes 1 and 2, index on axis 0
        if idx >= data.shape[0]:
            idx = data.shape[0] - 1
        slice_2d = data[idx, :, :]
    else:
        raise ValueError(f"Unknown plane: {selection.plane}")

    # Orient correctly (radiological convention)
    slice_2d = np.rot90(slice_2d)
    return slice_2d


def render_slice(
    nifti_path: str | Path,
    selection: SliceSelection,
    output_path: str | Path,
    volume_data: np.ndarray | None = None,
) -> Path:
    """
    Render a slice to a PNG image.

    Args:
        nifti_path: Path to the NIfTI file (used if volume_data is None)
        selection: Slice specification
        output_path: Output path for the PNG
        volume_data: Pre-loaded volume data (optional, to avoid reloading)

    Returns:
        Path to the generated PNG
    """
    output_path = Path(output_path)

    if volume_data is None:
        img = nib.load(str(nifti_path))
        volume_data = img.get_fdata()

    slice_2d = _extract_slice(volume_data, selection)
    normalized = _normalize_slice(slice_2d)

    fig, ax = plt.subplots(1, 1, figsize=PNG_SIZE_INCHES)
    ax.imshow(normalized, cmap='gray', aspect='equal', interpolation='bilinear')
    ax.axis('off')

    # Add light annotations
    label = (
        f"{selection.sequence.upper()} — {selection.plane.capitalize()} "
        f"(slice {selection.slice_index})"
    )
    ax.set_title(label, fontsize=9, color='white', pad=2,
                 bbox=dict(boxstyle='round,pad=0.3', facecolor='black', alpha=0.7))

    # Orientation markers
    if selection.plane == "axial":
        ax.text(0.02, 0.5, 'R', transform=ax.transAxes, fontsize=12,
                color='white', va='center', fontweight='bold')
        ax.text(0.97, 0.5, 'L', transform=ax.transAxes, fontsize=12,
                color='white', va='center', ha='right', fontweight='bold')
        ax.text(0.5, 0.98, 'A', transform=ax.transAxes, fontsize=12,
                color='white', ha='center', fontweight='bold')
        ax.text(0.5, 0.02, 'P', transform=ax.transAxes, fontsize=12,
                color='white', ha='center', fontweight='bold')
    elif selection.plane == "coronal":
        ax.text(0.02, 0.5, 'R', transform=ax.transAxes, fontsize=12,
                color='white', va='center', fontweight='bold')
        ax.text(0.97, 0.5, 'L', transform=ax.transAxes, fontsize=12,
                color='white', va='center', ha='right', fontweight='bold')
    elif selection.plane == "sagittal":
        ax.text(0.5, 0.98, 'A', transform=ax.transAxes, fontsize=12,
                color='white', ha='center', fontweight='bold')
        ax.text(0.5, 0.02, 'P', transform=ax.transAxes, fontsize=12,
                color='white', ha='center', fontweight='bold')

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=PNG_DPI, bbox_inches='tight',
                facecolor='black', edgecolor='none', pad_inches=0.1)
    plt.close(fig)

    return output_path


def render_all_slices(
    nifti_path: str | Path,
    selections: list[SliceSelection],
    output_dir: str | Path,
) -> list[tuple[SliceSelection, Path]]:
    """
    Render all selected slices to PNG.

    Returns:
        List of (selection, png_path) tuples
    """
    nifti_path = Path(nifti_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load the volume only once
    logger.info(f"Loading volume {nifti_path.name}...")
    img = nib.load(str(nifti_path))
    data = img.get_fdata()

    results = []
    for i, sel in enumerate(selections):
        filename = f"{sel.sequence}_{sel.plane}_{sel.slice_index:04d}.png"
        output_path = output_dir / filename

        try:
            render_slice(nifti_path, sel, output_path, volume_data=data)
            results.append((sel, output_path))
            logger.debug(f"  [{i+1}/{len(selections)}] {filename}")
        except Exception as e:
            logger.error(f"  Render error {filename}: {e}")

    logger.info(f"  {len(results)}/{len(selections)} slices rendered in {output_dir}")
    return results
