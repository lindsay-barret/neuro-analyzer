"""Parse DICOM files and identify sequences."""

import json
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict

import pydicom

from .config import SEQUENCE_PATTERNS

logger = logging.getLogger(__name__)


@dataclass
class SeriesInfo:
    """Information about a DICOM series."""
    series_number: int
    series_description: str
    protocol_name: str
    sequence_type: str  # t1_3d, t2, flair, swi, dwi, localizer, unknown
    modality: str
    acquisition_type: str  # 2D or 3D
    num_images: int
    slice_thickness: float
    pixel_spacing: list[float]
    rows: int
    columns: int
    repetition_time: float
    echo_time: float
    flip_angle: float
    folder_name: str  # e.g. SERIES1
    folder_path: str


@dataclass
class StudyInfo:
    """Information about the complete study."""
    patient_name: str
    patient_dob: str
    patient_sex: str
    patient_age: str
    patient_weight: float
    study_date: str
    study_description: str
    institution: str
    manufacturer: str
    model: str
    field_strength: float
    series: list[SeriesInfo] = field(default_factory=list)

    @property
    def t1_3d(self) -> SeriesInfo | None:
        """Return the T1 3D series (the most important one)."""
        candidates = [s for s in self.series if s.sequence_type == "t1_3d"]
        if not candidates:
            return None
        # Prefer the series with the most images (= best resolution)
        return max(candidates, key=lambda s: s.num_images)

    @property
    def swi(self) -> SeriesInfo | None:
        """Return the SWI series."""
        candidates = [s for s in self.series if s.sequence_type == "swi"]
        if not candidates:
            return None
        return max(candidates, key=lambda s: s.num_images)

    @property
    def flair(self) -> SeriesInfo | None:
        """Return the FLAIR series."""
        candidates = [s for s in self.series if s.sequence_type == "flair"]
        return candidates[0] if candidates else None

    @property
    def t2(self) -> SeriesInfo | None:
        """Return the T2 series."""
        candidates = [s for s in self.series if s.sequence_type == "t2"]
        return candidates[0] if candidates else None


def _classify_sequence(description: str, protocol: str, acq_type: str, num_images: int) -> str:
    """Classify a sequence from its description and parameters."""
    text = f"{description} {protocol}".lower()

    for seq_type, patterns in SEQUENCE_PATTERNS.items():
        for pattern in patterns:
            if pattern in text:
                # Extra check for T1 3D
                if seq_type == "t1_3d" and acq_type != "3D":
                    continue
                return seq_type

    # Heuristics based on the number of images
    if num_images < 10:
        return "localizer"

    return "unknown"


def parse_dicom_directory(dicom_dir: Path) -> StudyInfo:
    """
    Parse a DICOM directory and identify all sequences.

    Walks the standard PAT0/STUDY0/SERIES*/IM* structure.
    Reads the header of the first file in each series to identify the sequence.
    """
    dicom_dir = Path(dicom_dir)

    # Locate the Dicom folder if it exists
    if (dicom_dir / "Dicom").exists():
        dicom_root = dicom_dir / "Dicom"
    elif (dicom_dir / "DICOM").exists():
        dicom_root = dicom_dir / "DICOM"
    else:
        dicom_root = dicom_dir

    # Locate the SERIES folders
    series_folders = []
    for path in sorted(dicom_root.rglob("SERIES*")):
        if path.is_dir():
            series_folders.append(path)

    if not series_folders:
        # Try to find DICOM files directly
        raise FileNotFoundError(
            f"No SERIES folder found in {dicom_root}. "
            "Check that the DICOM directory has the PAT0/STUDY0/SERIES*/ structure"
        )

    logger.info(f"Found {len(series_folders)} series in {dicom_root}")

    study_info = None
    series_list = []

    for series_folder in series_folders:
        # Locate the first DICOM file in the series
        dicom_files = sorted([
            f for f in series_folder.iterdir()
            if f.is_file() and f.name.startswith("IM")
        ])

        if not dicom_files:
            logger.warning(f"No DICOM file in {series_folder}")
            continue

        num_images = len(dicom_files)

        try:
            ds = pydicom.dcmread(str(dicom_files[0]), stop_before_pixels=True)
        except Exception as e:
            logger.error(f"DICOM read error {dicom_files[0]}: {e}")
            continue

        # Extract study info (only once)
        if study_info is None:
            study_info = StudyInfo(
                patient_name=str(getattr(ds, 'PatientName', 'Unknown')),
                patient_dob=str(getattr(ds, 'PatientBirthDate', '')),
                patient_sex=str(getattr(ds, 'PatientSex', '')),
                patient_age=str(getattr(ds, 'PatientAge', '')),
                patient_weight=float(getattr(ds, 'PatientWeight', 0)),
                study_date=str(getattr(ds, 'StudyDate', '')),
                study_description=str(getattr(ds, 'StudyDescription', '')),
                institution=str(getattr(ds, 'InstitutionName', '')),
                manufacturer=str(getattr(ds, 'Manufacturer', '')),
                model=str(getattr(ds, 'ManufacturerModelName', '')),
                field_strength=float(getattr(ds, 'MagneticFieldStrength', 0)),
            )

        # Extract series info
        series_desc = str(getattr(ds, 'SeriesDescription', ''))
        protocol = str(getattr(ds, 'ProtocolName', ''))
        acq_type = str(getattr(ds, 'MRAcquisitionType', ''))

        seq_type = _classify_sequence(series_desc, protocol, acq_type, num_images)

        pixel_spacing = getattr(ds, 'PixelSpacing', [0, 0])
        pixel_spacing = [float(pixel_spacing[0]), float(pixel_spacing[1])]

        series_info = SeriesInfo(
            series_number=int(getattr(ds, 'SeriesNumber', 0)),
            series_description=series_desc,
            protocol_name=protocol,
            sequence_type=seq_type,
            modality=str(getattr(ds, 'Modality', '')),
            acquisition_type=acq_type,
            num_images=num_images,
            slice_thickness=float(getattr(ds, 'SliceThickness', 0)),
            pixel_spacing=pixel_spacing,
            rows=int(getattr(ds, 'Rows', 0)),
            columns=int(getattr(ds, 'Columns', 0)),
            repetition_time=float(getattr(ds, 'RepetitionTime', 0)),
            echo_time=float(getattr(ds, 'EchoTime', 0)),
            flip_angle=float(getattr(ds, 'FlipAngle', 0)),
            folder_name=series_folder.name,
            folder_path=str(series_folder),
        )

        series_list.append(series_info)
        logger.info(
            f"  {series_folder.name} → Series {series_info.series_number}: "
            f"{series_desc} [{seq_type}] ({num_images} images, {acq_type})"
        )

    if study_info is None:
        raise FileNotFoundError("No valid DICOM file found")

    study_info.series = series_list
    return study_info


def save_inventory(study: StudyInfo, output_path: Path):
    """Save the sequence inventory to JSON."""
    data = {
        "patient": {
            "name": study.patient_name,
            "dob": study.patient_dob,
            "sex": study.patient_sex,
            "age_at_scan": study.patient_age,
            "weight_kg": study.patient_weight,
        },
        "study": {
            "date": study.study_date,
            "description": study.study_description,
            "institution": study.institution,
            "scanner": f"{study.manufacturer} {study.model}",
            "field_strength_T": study.field_strength,
        },
        "series": [asdict(s) for s in study.series],
        "summary": {
            "total_series": len(study.series),
            "total_images": sum(s.num_images for s in study.series),
            "t1_3d_found": study.t1_3d is not None,
            "swi_found": study.swi is not None,
            "flair_found": study.flair is not None,
            "t2_found": study.t2 is not None,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info(f"Inventory saved to {output_path}")
