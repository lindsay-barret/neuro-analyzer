"""Disclaimer presence tests.

CLAUDE.md §3 mandates the bilingual ES/EN disclaimer at every user-facing
entry point. These tests assert the canonical anchors appear in:

  * the CLI ``--help`` output (rendered by Click from the cli() docstring)
  * the Markdown report produced by report_generator.generate_report
  * the Markdown report produced by quantify.generate_quantitative_report

The anchors are short and stable — they survive cosmetic rewording but
not deletion of the ES or EN block.
"""

from pathlib import Path

from click.testing import CliRunner

from neuro_analyzer.main import cli
from neuro_analyzer.report_generator import generate_report
from neuro_analyzer.quantify import QuantifyResult, generate_quantitative_report


# Stable anchors. Each must appear in every user-facing emission of the
# disclaimer. They are deliberately specific enough that an accidental
# deletion of the ES or EN block makes the test fail.
ES_ANCHOR = "INVESTIGACIÓN"
EN_ANCHOR = "RESEARCH AND EDUCATIONAL"


def test_cli_help_contains_bilingual_disclaimer():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0, f"--help exited with {result.exit_code}: {result.output}"
    assert ES_ANCHOR in result.output, "ES disclaimer anchor missing from CLI --help output"
    assert EN_ANCHOR in result.output, "EN disclaimer anchor missing from CLI --help output"


def test_generate_report_emits_bilingual_disclaimer(tmp_path: Path):
    # Minimal valid input: empty results, no study info, no context.
    # generate_report must still write a header containing the disclaimer.
    out = tmp_path / "report.md"
    generate_report(results=[], study_info=None, output_path=out, context=None)

    text = out.read_text(encoding="utf-8")
    assert ES_ANCHOR in text, "ES disclaimer anchor missing from generate_report output"
    assert EN_ANCHOR in text, "EN disclaimer anchor missing from generate_report output"


def test_generate_quantitative_report_emits_bilingual_disclaimer(tmp_path: Path):
    # Empty QuantifyResult: no FastSurfer needed. The function still emits
    # the header, the disclaimer, and the per-section scaffolding.
    out = tmp_path / "quantitative.md"
    generate_quantitative_report(result=QuantifyResult(), output_path=out, context=None)

    text = out.read_text(encoding="utf-8")
    assert ES_ANCHOR in text, "ES disclaimer anchor missing from generate_quantitative_report output"
    assert EN_ANCHOR in text, "EN disclaimer anchor missing from generate_quantitative_report output"
