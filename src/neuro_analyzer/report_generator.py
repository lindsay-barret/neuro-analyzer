"""Generate the final report from analysis results."""

import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .dicom_parser import StudyInfo
from .disclaimer import as_markdown_blockquote

logger = logging.getLogger(__name__)


def _count_findings(results: list[dict], key_path: list[str]) -> dict[str, int]:
    counts = defaultdict(int)
    for r in results:
        obj = r
        for key in key_path:
            obj = obj.get(key, {})
            if not obj:
                break
        if isinstance(obj, str):
            counts[obj] += 1
        elif isinstance(obj, list):
            for item in obj:
                counts[item] += 1
    return dict(counts)


def _aggregate_regions(results: list[dict], field: str) -> list[str]:
    regions = defaultdict(int)
    for r in results:
        obs = r.get("observations", {})
        region_list = obs.get(field, [])
        if isinstance(region_list, list):
            for region in region_list:
                regions[region] += 1
    return sorted(regions.keys(), key=lambda x: regions[x], reverse=True)


def _report_title(study_info: StudyInfo | None, context: dict | None) -> str:
    """Choose a non-PHI title for the report.

    Preference order: explicit ``report_title`` from context, generic
    "Brain MRI analysis — <patient_name from DICOM>" if present, else
    fully generic "Brain MRI analysis".
    """
    if context:
        explicit = context.get("report_title")
        if explicit:
            return f"# {str(explicit).strip()}"
    if study_info and study_info.patient_name:
        return f"# Brain MRI analysis — {study_info.patient_name}"
    return "# Brain MRI analysis"


def _render_clinical_correlation(context: dict | None) -> list[str]:
    """Render the optional clinical-correlation section.

    Iterates over ``context.clinical_correlation`` (a dict whose values are
    free-form prose blocks) and emits one ``###`` subsection per non-empty
    entry. Returns an empty list when nothing is provided — the caller
    should then skip the section heading entirely rather than emit a
    placeholder.
    """
    out: list[str] = []
    if not context:
        return out
    cc = context.get("clinical_correlation") or {}
    if not isinstance(cc, dict):
        return out

    # Friendly labels for known sub-keys; arbitrary user keys fall through
    # using their key name title-cased.
    known = {
        "eeg": "EEG correlation",
        "development": "Developmental correlation",
        "imaging_history": "Imaging history correlation",
        "genetics": "Genetic correlation",
    }

    for key, value in cc.items():
        if not value:
            continue
        text = str(value).strip()
        if not text:
            continue
        heading = known.get(key, key.replace("_", " ").capitalize())
        out.append(f"### {heading}")
        out.append(text)
        out.append("")
    return out


def generate_report(
    results: list[dict],
    study_info: StudyInfo | None,
    output_path: Path,
    context: dict | None = None,
):
    """Generate the final report in Markdown.

    Args:
        results: Per-slice analysis results (list of dicts).
        study_info: DICOM study metadata (may be None when regenerating
            from saved JSON without re-parsing).
        output_path: where to write the .md file.
        context: optional dict (see ``config.load_patient_context``). May
            contain ``report_title``, ``clinical_correlation`` (dict of
            free-form prose blocks). When omitted, the corresponding
            sections are skipped.
    """
    t1_results = [r for r in results if r.get("slice_id", "").startswith("t1")]
    swi_results = [r for r in results if r.get("slice_id", "").startswith("swi")]
    error_results = [r for r in results if "error" in r]
    valid_results = [r for r in results if "error" not in r]

    abnormal_regions = _aggregate_regions(valid_results, "regions_clearly_abnormal")
    normal_regions = _aggregate_regions(valid_results, "regions_clearly_normal")
    uncertain_regions = _aggregate_regions(valid_results, "regions_uncertain")

    cortical_severity = _count_findings(valid_results, ["observations", "cortical_thickness", "severity"])
    gyrification_pattern = _count_findings(valid_results, ["observations", "gyrification", "pattern"])
    gw_clarity = _count_findings(valid_results, ["observations", "grey_white_interface", "clarity"])
    laterality = _count_findings(valid_results, ["observations", "cortical_thickness", "laterality"])

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    report = []
    report.append(_report_title(study_info, context))
    report.append("")
    report.append(f"**Report date**: {now}")
    report.append("")
    report.append(as_markdown_blockquote())
    report.append("")

    # --- Section 1: Acquisition technical data ---
    report.append("## 1. Acquisition technical data")
    report.append("")
    if study_info:
        report.append("| Parameter | Value |")
        report.append("|---|---|")
        report.append(f"| Subject | {study_info.patient_name} |")
        report.append(f"| Date of birth | {study_info.patient_dob} |")
        report.append(f"| Age at MRI | {study_info.patient_age} |")
        report.append(f"| Weight | {study_info.patient_weight} kg |")
        report.append(f"| Study date | {study_info.study_date} |")
        report.append(f"| Scanner | {study_info.manufacturer} {study_info.model} |")
        report.append(f"| Field strength | {study_info.field_strength}T |")
        report.append(f"| Institution | {study_info.institution} |")
        report.append(f"| Description | {study_info.study_description} |")
        report.append("")

    # --- Section 2: Sequence inventory ---
    report.append("## 2. Sequence inventory")
    report.append("")
    if study_info:
        report.append("| Series | Description | Type | Images | Resolution |")
        report.append("|---|---|---|---|---|")
        for s in study_info.series:
            px = f"{s.pixel_spacing[0]:.2f}×{s.pixel_spacing[1]:.2f}×{s.slice_thickness:.1f} mm"
            report.append(f"| {s.series_number} | {s.series_description} | {s.sequence_type} | {s.num_images} | {px} |")
        report.append("")

    # --- Section 3: Observations summary ---
    report.append("## 3. Observations summary")
    report.append("")
    report.append("### Slices analyzed")
    report.append(f"- Total: {len(results)} slices sent to analysis")
    report.append(f"- T1: {len(t1_results)} slices")
    report.append(f"- SWI: {len(swi_results)} slices")
    report.append(f"- Errors: {len(error_results)} slices not analyzed")
    report.append("")

    report.append("### Cortical thickness")
    report.append("Severity distribution across slices:")
    report.append("")
    for severity, count in sorted(cortical_severity.items(), key=lambda x: x[1], reverse=True):
        report.append(f"- **{severity}**: {count} slices")
    report.append("")

    report.append("### Gyrification pattern")
    for pattern, count in sorted(gyrification_pattern.items(), key=lambda x: x[1], reverse=True):
        report.append(f"- **{pattern}**: {count} slices")
    report.append("")

    report.append("### Gray-white interface")
    for clarity, count in sorted(gw_clarity.items(), key=lambda x: x[1], reverse=True):
        report.append(f"- **{clarity}**: {count} slices")
    report.append("")

    report.append("### Laterality")
    for lat, count in sorted(laterality.items(), key=lambda x: x[1], reverse=True):
        report.append(f"- **{lat}**: {count} slices")
    report.append("")

    # --- Section 4: Abnormality mapping ---
    report.append("## 4. Observed abnormality mapping")
    report.append("")
    report.append("### Clearly abnormal regions")
    if abnormal_regions:
        for region in abnormal_regions:
            report.append(f"- {region}")
    else:
        report.append("- No region identified as clearly abnormal")
    report.append("")

    report.append("### Clearly normal regions")
    if normal_regions:
        for region in normal_regions:
            report.append(f"- {region}")
    else:
        report.append("- No region identified as clearly normal")
    report.append("")

    report.append("### Uncertain regions")
    if uncertain_regions:
        for region in uncertain_regions:
            report.append(f"- {region}")
    report.append("")

    # --- Section 5: Detailed analysis by plane ---
    for plane_name, plane_results in [
        ("axial", [r for r in t1_results if r.get("plane") == "axial"]),
        ("coronal", [r for r in t1_results if r.get("plane") == "coronal"]),
        ("sagittal", [r for r in t1_results if r.get("plane") == "sagittal"]),
    ]:
        if not plane_results:
            continue

        report.append(f"## 5. Detailed analysis — {plane_name.capitalize()} T1 slices")
        report.append("")

        for r in plane_results:
            if "error" in r:
                continue
            slice_id = r.get("slice_id", "?")
            level = r.get("anatomical_level", "?")
            report.append(f"### {slice_id}")
            report.append(f"**Level**: {level}")
            report.append("")

            obs = r.get("observations", {})

            ct = obs.get("cortical_thickness", {})
            if ct:
                report.append(f"- **Cortical thickness**: {ct.get('description', 'N/A')} "
                              f"(severity: {ct.get('severity', '?')}, laterality: {ct.get('laterality', '?')})")

            gyr = obs.get("gyrification", {})
            if gyr:
                report.append(f"- **Gyrification**: {gyr.get('description', 'N/A')} "
                              f"(pattern: {gyr.get('pattern', '?')})")

            gwi = obs.get("grey_white_interface", {})
            if gwi:
                report.append(f"- **G/W interface**: {gwi.get('description', 'N/A')} "
                              f"(clarity: {gwi.get('clarity', '?')})")

            asym = obs.get("asymmetry", {})
            if asym:
                report.append(f"- **Asymmetry**: {'Yes' if asym.get('present') else 'No'} — "
                              f"{asym.get('description', '')}")

            additional = obs.get("additional_findings", [])
            if additional:
                report.append(f"- **Additional findings**: {', '.join(additional)}")

            relevance = r.get("clinical_relevance", "")
            if relevance:
                report.append(f"- **Clinical relevance**: {relevance}")

            report.append("")

    # --- Section 6: SWI ---
    if swi_results:
        report.append("## 6. SWI analysis (Susceptibility Weighted Imaging)")
        report.append("")
        for r in swi_results:
            if "error" in r:
                continue
            slice_id = r.get("slice_id", "?")
            level = r.get("anatomical_level", "?")
            report.append(f"### {slice_id}")
            report.append(f"**Level**: {level}")
            obs = r.get("observations", {})
            additional = obs.get("additional_findings", [])
            if additional:
                for finding in additional:
                    report.append(f"- {finding}")
            else:
                report.append("- No susceptibility abnormality noted")
            report.append("")

    # --- Section 7: Clinical correlation (optional, from context) ---
    correlation_lines = _render_clinical_correlation(context)
    if correlation_lines:
        report.append("## 7. Correlation with clinical record")
        report.append("")
        report.extend(correlation_lines)

    # --- Limitations ---
    report.append("## Limitations of this analysis")
    report.append("")
    report.append("1. **AI is not a radiologist.** The model can describe visual patterns "
                  "but lacks the training and experience of a pediatric neuroradiologist.")
    report.append("2. **2D analysis of 3D data.** Each slice is analyzed independently, "
                  "without volumetric reconstruction or segmentation.")
    report.append("3. **No quantitative measurements in this section.** Terms such as "
                  "'thickened', 'reduced', etc. are qualitative. For objective measurements, "
                  "use the `quantify` command (FastSurfer).")
    report.append("4. **Pediatric brain.** The child's brain has a myelination and "
                  "gyrification pattern different from adults, complicating interpretation "
                  "by models trained predominantly on adult data.")
    report.append("5. **No comparison with a normative pediatric atlas.**")
    report.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report))

    logger.info(f"Report generated: {output_path}")
    return output_path
