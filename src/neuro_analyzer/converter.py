"""DICOM to NIfTI conversion via dcm2niix."""

import logging
import shutil
import subprocess
from pathlib import Path

from .dicom_parser import SeriesInfo

logger = logging.getLogger(__name__)


def check_dcm2niix() -> bool:
    """Check that dcm2niix is installed and accessible."""
    if shutil.which("dcm2niix") is not None:
        return True
    # Chercher dans des emplacements courants sur Windows
    common_paths = [
        Path.home() / "dcm2niix" / "dcm2niix.exe",
        Path("C:/dcm2niix/dcm2niix.exe"),
        Path("C:/Program Files/dcm2niix/dcm2niix.exe"),
    ]
    for p in common_paths:
        if p.exists():
            return True
    return False


def get_dcm2niix_path() -> str:
    """Return the path to dcm2niix."""
    which = shutil.which("dcm2niix")
    if which:
        return which
    common_paths = [
        Path.home() / "dcm2niix" / "dcm2niix.exe",
        Path("C:/dcm2niix/dcm2niix.exe"),
        Path("C:/Program Files/dcm2niix/dcm2niix.exe"),
    ]
    for p in common_paths:
        if p.exists():
            return str(p)
    raise FileNotFoundError(
        "dcm2niix not found. Install from:\n"
        "  https://github.com/rordenlab/dcm2niix/releases\n"
        "  Windows: extract the .exe and add it to PATH\n"
        "  macOS: brew install dcm2niix\n"
        "  Linux: sudo apt install dcm2niix"
    )


def convert_series(series: SeriesInfo, output_dir: Path) -> Path | None:
    """
    Convert a DICOM series to NIfTI.

    Returns:
        Path to the generated .nii.gz file, or None on error.
    """
    dcm2niix = get_dcm2niix_path()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Output name based on the sequence type
    output_name = f"{series.sequence_type}_series{series.series_number}"

    cmd = [
        dcm2niix,
        "-z", "y",           # gzip compression
        "-f", output_name,   # output name
        "-o", str(output_dir),
        "-b", "y",           # generate the .json file (bids sidecar)
        "-w", "1",           # overwrite if exists
        str(series.folder_path),
    ]

    logger.info(f"Converting {series.series_description} (Series {series.series_number})...")
    logger.debug(f"Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes max
        )

        if result.returncode != 0:
            logger.error(f"dcm2niix error: {result.stderr}")
            return None

        logger.debug(f"dcm2niix stdout: {result.stdout}")

    except subprocess.TimeoutExpired:
        logger.error("dcm2niix timeout (>5 min)")
        return None
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        return None

    # Locate the generated NIfTI file
    nifti_files = list(output_dir.glob(f"{output_name}*.nii.gz"))
    if not nifti_files:
        # dcm2niix sometimes adds suffixes
        nifti_files = list(output_dir.glob(f"{output_name}*.nii*"))

    if not nifti_files:
        logger.error(f"No NIfTI file generated for {series.series_description}")
        return None

    nifti_path = nifti_files[0]
    logger.info(f"  → {nifti_path.name} ({nifti_path.stat().st_size / 1024 / 1024:.1f} MB)")
    return nifti_path


def convert_study(series_list: list[SeriesInfo], output_dir: Path,
                  sequence_types: list[str] | None = None) -> dict[str, Path]:
    """
    Convert the selected series of a study.

    Args:
        series_list: List of series to convert
        output_dir: Output directory for the NIfTI files
        sequence_types: Sequence types to convert (None = all)

    Returns:
        Dictionary {sequence_type: nifti_path}
    """
    if not check_dcm2niix():
        raise FileNotFoundError(get_dcm2niix_path())  # Will raise with install instructions

    results = {}

    for series in series_list:
        if sequence_types and series.sequence_type not in sequence_types:
            logger.debug(f"Skip {series.series_description} (type {series.sequence_type})")
            continue

        if series.sequence_type in ("localizer", "unknown"):
            logger.debug(f"Skip {series.series_description} (type {series.sequence_type})")
            continue

        nifti_path = convert_series(series, output_dir)
        if nifti_path:
            results[f"{series.sequence_type}_{series.series_number}"] = nifti_path

    logger.info(f"Conversion complete: {len(results)} NIfTI files")
    return results
