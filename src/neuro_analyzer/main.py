"""CLI entry point for Neuro-Analyzer.

THIS TOOL IS FOR RESEARCH AND EDUCATIONAL PURPOSES ONLY.
NOT APPROVED BY ANY REGULATORY AUTHORITY (FDA, EMA, COFEPRIS, etc.).
NOT INTENDED FOR CLINICAL DIAGNOSIS OR TREATMENT DECISIONS.
"""

import json
import logging
import os
import sys
from pathlib import Path

# Force UTF-8 on Windows to avoid Rich/cp1252 encoding errors
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

import click
from rich.console import Console
from rich.table import Table
from rich.logging import RichHandler

from .config import AnalysisConfig, API_MODEL, CONTEXT_ENV_VAR, load_patient_context
from .dicom_parser import parse_dicom_directory, save_inventory
from .converter import convert_study, check_dcm2niix
from .slice_selector import select_slices_for_volume
from .slice_renderer import render_all_slices
from .vision_analyzer import analyze_all_slices
from .report_generator import generate_report
from .quantify import (
    find_t1_nifti, check_docker, pull_fastsurfer_image,
    run_fastsurfer, extract_results, generate_quantitative_report,
    _check_segmentation_qc,
)
from .exceptions import SegmentationCorruptedError
from .disclaimer import DISCLAIMER_BILINGUAL

console = Console()


DISCLAIMER_BANNER = "[yellow]" + DISCLAIMER_BILINGUAL + "[/]"


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def _resolve_context_path(cli_value: str | None) -> Path | None:
    """Resolve the context file path: CLI flag wins, else env var, else None."""
    if cli_value:
        return Path(cli_value)
    env_value = os.environ.get(CONTEXT_ENV_VAR)
    if env_value:
        return Path(env_value)
    return None


def _load_context_or_exit(path: Path | None) -> dict:
    """Load context with friendly error handling."""
    try:
        return load_patient_context(path)
    except (FileNotFoundError, ValueError, ImportError) as e:
        console.print(f"[bold red]Error:[/] {e}")
        sys.exit(2)


# Common --context-file decorator factory
def _context_option(f):
    return click.option(
        "--context-file",
        type=click.Path(),
        default=None,
        help="YAML file describing the case (optional). Without it, generic "
             "fallbacks are used. Env var: " + CONTEXT_ENV_VAR + ".",
    )(f)


@click.group()
def cli():
    """Neuro-Analyzer — Pediatric MRI re-analysis pipeline.

    \b
    ESTA HERRAMIENTA ES PARA INVESTIGACIÓN Y EDUCACIÓN ÚNICAMENTE.
    NO ESTÁ APROBADA POR COFEPRIS, FDA, EMA NI NINGUNA AUTORIDAD SANITARIA.
    NO DEBE UTILIZARSE PARA DIAGNÓSTICO, TRATAMIENTO O TOMA DE DECISIONES CLÍNICAS.

    \b
    THIS TOOL IS FOR RESEARCH AND EDUCATIONAL PURPOSES ONLY.
    NOT APPROVED BY ANY REGULATORY AUTHORITY (FDA, EMA, COFEPRIS, ETC.).
    NOT INTENDED FOR CLINICAL DIAGNOSIS OR TREATMENT DECISIONS.
    """
    console.print(DISCLAIMER_BANNER)


@cli.command()
@click.argument("input_dir", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default=None, help="Output directory")
@click.option("--max-slices", type=int, default=None, help="Maximum number of slices to analyze")
@click.option("--model", default=API_MODEL, help="Claude model to use")
@_context_option
@click.option("--verbose", "-v", is_flag=True, help="Verbose mode")
def scan(input_dir, output, max_slices, model, context_file, verbose):
    """Complete analysis: parse → convert → slice → analyze → report."""
    setup_logging(verbose)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[bold red]Error:[/] ANTHROPIC_API_KEY environment variable is not set.")
        console.print("Configure with: export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)

    if not check_dcm2niix():
        console.print("[bold red]Error:[/] dcm2niix not found.")
        console.print("Install from: https://github.com/rordenlab/dcm2niix/releases")
        sys.exit(1)

    context = _load_context_or_exit(_resolve_context_path(context_file))

    config = AnalysisConfig(
        input_dir=input_dir,
        output_dir=Path(output) if output else None,
        max_slices=max_slices,
        model=model,
        verbose=verbose,
        context_file=Path(context_file) if context_file else None,
    )
    config.ensure_dirs()

    # === Step 1: Inventory ===
    console.print("\n[bold cyan]═══ STEP 1/5: DICOM inventory ═══[/]\n")
    study = parse_dicom_directory(config.input_dir)
    save_inventory(study, config.inventory_path)
    _print_study_table(study)

    if not study.t1_3d:
        console.print("[bold red]Fatal error:[/] No 3D T1 sequence found.")
        console.print("Analysis requires at minimum a volumetric 3D T1.")
        sys.exit(1)

    # === Step 2: DICOM to NIfTI conversion ===
    console.print("\n[bold cyan]═══ STEP 2/5: DICOM to NIfTI conversion ═══[/]\n")
    sequences_to_convert = ["t1_3d"]
    if study.swi:
        sequences_to_convert.append("swi")

    nifti_files = convert_study(study.series, config.nifti_dir, sequences_to_convert)

    if not nifti_files:
        console.print("[bold red]Error:[/] No NIfTI file generated.")
        sys.exit(1)

    for key, path in nifti_files.items():
        console.print(f"  ✓ {key} → {path.name}")

    # === Step 3: Slice selection ===
    console.print("\n[bold cyan]═══ STEP 3/5: Slice selection ═══[/]\n")
    all_selections = []

    for key, nifti_path in nifti_files.items():
        seq_type = key.split("_")[0]
        if "t1" in key:
            seq_type = "t1"
        elif "swi" in key:
            seq_type = "swi"

        selections = select_slices_for_volume(
            str(nifti_path),
            seq_type,
            max_slices=config.max_slices,
        )
        all_selections.extend([(sel, nifti_path) for sel in selections])
        console.print(f"  {key}: {len(selections)} slices selected")

    # === Step 4: PNG rendering ===
    console.print("\n[bold cyan]═══ STEP 4/5: Slice rendering ═══[/]\n")
    all_rendered = []

    for nifti_path in set(path for _, path in all_selections):
        sels = [sel for sel, p in all_selections if p == nifti_path]
        rendered = render_all_slices(nifti_path, sels, config.slices_dir)
        all_rendered.extend(rendered)

    console.print(f"  Total: {len(all_rendered)} slices rendered to PNG")

    # === Step 5: Vision analysis ===
    console.print("\n[bold cyan]═══ STEP 5/5: Analysis by Claude Vision ═══[/]\n")
    console.print(f"  Model: {config.model}")
    console.print(f"  Slices to analyze: {len(all_rendered)}")
    console.print(f"  Estimated cost: ~${len(all_rendered) * 0.05:.2f} USD\n")

    results = analyze_all_slices(all_rendered, config.analysis_dir, config.model, context=context)

    # === Report ===
    console.print("\n[bold cyan]═══ Report generation ═══[/]\n")
    generate_report(results, study, config.report_path, context=context)

    console.print("\n[bold green]✓ Analysis complete![/]")
    console.print(f"  Report: {config.report_path}")
    console.print(f"  Slices: {config.slices_dir}")
    console.print(f"  JSON analyses: {config.analysis_dir}")


@cli.command()
@click.argument("input_dir", type=click.Path(exists=True))
@click.option("--verbose", "-v", is_flag=True)
def inventory(input_dir, verbose):
    """Scan DICOM files and identify sequences."""
    setup_logging(verbose)

    study = parse_dicom_directory(Path(input_dir))
    _print_study_table(study)

    output_path = Path(input_dir) / "neuro_analysis" / "inventory.json"
    save_inventory(study, output_path)
    console.print(f"\nInventory saved: {output_path}")


@cli.command()
@click.argument("input_dir", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default=None)
@click.option("--verbose", "-v", is_flag=True)
def convert(input_dir, output, verbose):
    """Convert DICOM to NIfTI."""
    setup_logging(verbose)

    if not check_dcm2niix():
        console.print("[bold red]Error:[/] dcm2niix not found.")
        sys.exit(1)

    study = parse_dicom_directory(Path(input_dir))
    output_dir = Path(output) if output else Path(input_dir) / "neuro_analysis" / "nifti"

    nifti_files = convert_study(study.series, output_dir)
    for key, path in nifti_files.items():
        console.print(f"  ✓ {key} → {path.name}")


@cli.command()
@click.argument("input_dir", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default=None)
@click.option("--max-slices", type=int, default=None)
@click.option("--verbose", "-v", is_flag=True)
def slices(input_dir, output, max_slices, verbose):
    """Generate PNG slices from NIfTI files."""
    setup_logging(verbose)

    nifti_dir = Path(input_dir) / "neuro_analysis" / "nifti"
    if not nifti_dir.exists():
        console.print("[bold red]Error:[/] NIfTI directory not found. Run 'convert' first.")
        sys.exit(1)

    output_dir = Path(output) if output else Path(input_dir) / "neuro_analysis" / "slices"

    for nifti_path in nifti_dir.glob("*.nii.gz"):
        seq_type = "t1" if "t1" in nifti_path.stem else nifti_path.stem.split("_")[0]
        selections = select_slices_for_volume(str(nifti_path), seq_type, max_slices)
        rendered = render_all_slices(nifti_path, selections, output_dir)
        console.print(f"  {nifti_path.name}: {len(rendered)} slices")


@cli.command()
@click.argument("slices_dir", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default=None)
@click.option("--model", default=API_MODEL)
@_context_option
@click.option("--verbose", "-v", is_flag=True)
def analyze(slices_dir, output, model, context_file, verbose):
    """Analyze existing PNG slices via Claude Vision."""
    setup_logging(verbose)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[bold red]Error:[/] ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    context = _load_context_or_exit(_resolve_context_path(context_file))

    slices_path = Path(slices_dir)
    output_dir = Path(output) if output else slices_path.parent / "analysis"

    from .slice_selector import SliceSelection
    slice_results = []
    for png in sorted(slices_path.glob("*.png")):
        parts = png.stem.split("_")
        if len(parts) >= 3:
            seq = parts[0]
            plane = parts[1]
            idx = int(parts[2])
            sel = SliceSelection(
                slice_index=idx, plane=plane, sequence=seq,
                position_fraction=0.5, is_focal=True, anatomical_level="unknown"
            )
            slice_results.append((sel, png))

    console.print(f"  {len(slice_results)} slices found")
    results = analyze_all_slices(slice_results, output_dir, model, context=context)
    console.print(f"  {len(results)} slices analyzed")


@cli.command()
@click.argument("analysis_dir", type=click.Path(exists=True))
@click.option("--input-dir", type=click.Path(), default=None, help="Original DICOM directory")
@click.option("--output", "-o", type=click.Path(), default=None)
@_context_option
@click.option("--verbose", "-v", is_flag=True)
def report(analysis_dir, input_dir, output, context_file, verbose):
    """Generate report from existing analysis results."""
    setup_logging(verbose)

    context = _load_context_or_exit(_resolve_context_path(context_file))

    analysis_path = Path(analysis_dir)

    results = []
    for json_file in sorted(analysis_path.glob("*.json")):
        if json_file.name == "inventory.json":
            continue
        with open(json_file, "r", encoding="utf-8") as f:
            results.append(json.load(f))

    study = None
    if input_dir:
        try:
            study = parse_dicom_directory(Path(input_dir))
        except Exception:
            pass

    output_path = Path(output) if output else analysis_path.parent / "report.md"
    generate_report(results, study, output_path, context=context)
    console.print(f"Report generated: {output_path}")


@cli.command()
@click.argument("nifti_dir", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default=None,
              help="FastSurfer output directory")
@click.option("--report-path", type=click.Path(), default=None,
              help="Path to the quantitative report (.md)")
@click.option("--subject-id", default="sub-01",
              help="FastSurfer subject ID (BIDS-style, e.g. sub-01)")
@click.option("--threads", type=int, default=8, help="Number of CPU threads")
@click.option("--timeout", type=int, default=180, help="Timeout in minutes per pass")
@click.option("--skip-fastsurfer", is_flag=True,
              help="Skip FastSurfer and use existing results")
@click.option("--surf-only", is_flag=True,
              help="Run only the surface pass (segmentation already done)")
@click.option("--fs-license", type=click.Path(), default=None,
              help="Path to the FreeSurfer license.txt file (required for surface/thickness/LGI)")
@_context_option
@click.option("--verbose", "-v", is_flag=True)
def quantify(nifti_dir, output, report_path, subject_id, threads, timeout,
             skip_fastsurfer, surf_only, fs_license, context_file, verbose):
    """Quantitative analysis via FastSurfer: volumetry, cortical thickness, LGI."""
    setup_logging(verbose)

    context = _load_context_or_exit(_resolve_context_path(context_file))

    nifti_path = Path(nifti_dir)

    t1_file = find_t1_nifti(nifti_path)
    if t1_file is None:
        console.print("[bold red]Error:[/] No 3D T1 file (t1_3d*.nii.gz) found in the directory.")
        sys.exit(1)
    console.print(f"  3D T1 found: [cyan]{t1_file.name}[/]")

    output_dir = Path(output) if output else nifti_path.parent / "fastsurfer"

    if report_path is None:
        report_file = nifti_path.parent / "quantitative_report.md"
    else:
        report_file = Path(report_path)

    if not skip_fastsurfer:
        console.print("\n[bold cyan]═══ Docker check ═══[/]\n")
        if not check_docker():
            console.print("[bold red]Error:[/] Docker is not installed or not running.")
            console.print("Install Docker Desktop: https://www.docker.com/products/docker-desktop/")
            sys.exit(1)
        console.print("  [green]✓[/] Docker operational")

        console.print("\n[bold cyan]═══ FastSurfer image ═══[/]\n")
        if not pull_fastsurfer_image():
            console.print("[bold red]Error:[/] Unable to pull image deepmi/fastsurfer:latest.")
            sys.exit(1)
        console.print("  [green]✓[/] Image deepmi/fastsurfer:latest ready")

        console.print("\n[bold cyan]═══ FastSurfer execution ═══[/]\n")
        console.print(f"  Subject: {subject_id}")
        console.print(f"  Threads: {threads}")
        console.print(f"  Output: {output_dir}")
        console.print("")
        if surf_only:
            console.print("  [yellow]⏳ Surface pass only (existing segmentation)...[/]")
        else:
            console.print("  [yellow]⏳ FastSurfer running — this can take 30 min to 2h...[/]")
            console.print("  [dim]  (segmentation + surface reconstruction)[/]")
        console.print("")

        fs_license_path = Path(fs_license) if fs_license else None

        if fs_license_path:
            console.print(f"  FreeSurfer license: {fs_license_path}")
        else:
            console.print("  [yellow]No FreeSurfer license — surface pass disabled[/]")
            console.print("  [dim]  (volumetry only, no cortical thickness or LGI)[/]")

        if surf_only and not fs_license_path:
            console.print("[bold red]Error:[/] --surf-only requires --fs-license")
            sys.exit(1)

        success, log = run_fastsurfer(
            t1_path=t1_file,
            output_dir=output_dir,
            subject_id=subject_id,
            threads=threads,
            timeout_minutes=timeout,
            fs_license=fs_license_path,
            surf_only=surf_only,
        )

        log_path = output_dir / "fastsurfer_run.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(log, encoding="utf-8")

        if not success:
            console.print("[bold red]Error:[/] FastSurfer segmentation failed.")
            console.print(f"  Log: {log_path}")
            sys.exit(1)

        console.print("  [green]✓[/] FastSurfer complete")
    else:
        console.print("  [yellow]FastSurfer skipped (--skip-fastsurfer)[/]")

    console.print("\n[bold cyan]═══ Results extraction ═══[/]\n")

    subj_stats_dir = output_dir / subject_id / "stats"
    if not subj_stats_dir.exists():
        console.print(f"[bold red]Error:[/] stats directory not found: {subj_stats_dir}")
        console.print("Check that FastSurfer completed correctly.")
        sys.exit(1)

    qc_failure = _check_segmentation_qc(output_dir, subject_id)
    if qc_failure is not None:
        err = SegmentationCorruptedError(qc_failure)
        console.print(f"[bold red]{err}[/]")
        sys.exit(SegmentationCorruptedError.EXIT_CODE)

    result = extract_results(output_dir, subject_id)

    n_cortical = len(result.cortical_regions)
    n_subcortical = len(result.subcortical)
    console.print(f"  Cortical regions: {n_cortical}")
    console.print(f"  Subcortical structures: {n_subcortical}")
    console.print(f"  LGI available: {'yes' if result.lgi_available else 'no'}")

    console.print("\n[bold cyan]═══ Report generation ═══[/]\n")
    generate_quantitative_report(result, report_file, context=context)

    console.print("\n[bold green]✓ Quantitative analysis complete![/]")
    console.print(f"  Report: {report_file}")
    console.print(f"  FastSurfer data: {output_dir / subject_id}")


def _print_study_table(study):
    """Print a summary table for the study."""
    console.print(f"\n[bold]Subject[/]: {study.patient_name}")
    console.print(f"[bold]Date[/]: {study.study_date}")
    console.print(f"[bold]Scanner[/]: {study.manufacturer} {study.model} ({study.field_strength}T)")
    console.print(f"[bold]Institution[/]: {study.institution}")

    table = Table(title="Identified sequences")
    table.add_column("Series", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Type", style="green")
    table.add_column("Images", justify="right")
    table.add_column("Acq.", style="yellow")
    table.add_column("Resolution")

    for s in study.series:
        type_style = "bold green" if s.sequence_type in ("t1_3d", "swi") else "white"
        px = f"{s.pixel_spacing[0]:.2f}×{s.pixel_spacing[1]:.2f}×{s.slice_thickness:.1f}"
        table.add_row(
            str(s.series_number),
            s.series_description or s.protocol_name,
            f"[{type_style}]{s.sequence_type}[/]",
            str(s.num_images),
            s.acquisition_type,
            px,
        )

    console.print(table)

    if study.t1_3d:
        console.print(f"\n  [green]✓[/] 3D T1 found: {study.t1_3d.series_description}")
    else:
        console.print("\n  [red]✗[/] 3D T1 NOT FOUND — analysis not possible")

    if study.swi:
        console.print(f"  [green]✓[/] SWI found: {study.swi.series_description}")


if __name__ == "__main__":
    cli()
