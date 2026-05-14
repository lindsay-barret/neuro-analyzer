# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-05-15

Initial public release. This is a research and educational tool, not a medical
device. See [`DISCLAIMER.md`](DISCLAIMER.md) for full terms.

### Added

- DICOM → NIfTI conversion via `dcm2niix`.
- Structural MRI quantitative re-analysis pipeline orchestrating FastSurfer
  (Docker, CPU-only `seg_only` mode, no FreeSurfer license required for the
  default workflow).
- Regional volumetry and cortical thickness reporting from FastSurfer
  `aseg+DKT` outputs.
- Optional Local Gyrification Index (LGI) computation via FreeSurfer,
  isolated in `optional/freesurfer_lgi.py`. FreeSurfer is **not** bundled;
  users must install it independently under its own academic license.
- AI-assisted qualitative slice analysis via the Anthropic Claude Vision API,
  with parameterizable diagnostic focus and per-sequence notes loaded from a
  user-supplied YAML context file.
- Structural MRI slice selection (axial / coronal / sagittal) with focal-region
  density weighting.
- Markdown report generation aggregating per-slice findings and (optionally)
  clinical correlation provided in the context file.
- Bilingual ES/EN medical disclaimer centralized in
  `src/neuro_analyzer/disclaimer.py` and injected into all user-facing entry
  points (CLI, generated reports).
- Example context file in `examples/` and per-field documentation.
- MIT License, contributor guide, citation metadata (`CITATION.cff`), and
  long-form medical/regulatory disclaimer.

### Validation

- End-to-end pipeline execution verified on one healthy pediatric subject
  from the public [OpenNeuro ds000228](https://openneuro.org/datasets/ds000228)
  dataset (subject `sub-pixar066`). This demonstrates that the pipeline runs
  on independent external data — it does **not** constitute clinical
  validation, accuracy benchmarking against a reference method, performance
  evaluation on pathological cases, or statistical reproducibility (n=1).

### Security

- No patient data, identifiers, or API keys committed to the repository.
- `.gitignore` blocks DICOM/NIfTI formats, patient context files, and
  FreeSurfer license files by default.
- Pre-commit hooks enforced locally and in CI:
  - `gitleaks` (secret scanning)
  - `forbidden-patterns` (custom hook blocking identifying patterns)
  - `detect-private-key`
  - `check-added-large-files` (500 KB limit)
  - `ruff` (Python linting)
- GitHub Actions CI on push and pull request:
  - Lint job: full-history `gitleaks` scan and `ruff` checks on Python 3.11
  - Test matrix: `pytest` across Python 3.10, 3.11, 3.12, 3.13 on
    `ubuntu-latest`

### Project Governance

- Project scope intentionally narrow. Out-of-scope contributions explicitly
  listed in [`CONTRIBUTING.md`](CONTRIBUTING.md) to prevent drift toward
  clinical device or SaaS positioning. Excluded by policy: regulatory claims,
  diagnostic outputs, clinical decision support, FreeSurfer bundling,
  removal or weakening of medical disclaimers.
- Maintenance horizon stated openly: active maintenance through end of 2027,
  after which the repository will be archived in read-only state with its
  Zenodo DOI permanently citable. Documented in [`README.md`](README.md).

### Known Limitations

- FastSurfer is trained predominantly on adult cohorts and may produce
  segmentation errors on pediatric brains and on cortex with significant
  malformations.
- Z-scores are computed against adult reference atlases by default;
  pediatric-specific atlases are not yet integrated.
- AI-assisted visual analysis (Claude API) is probabilistic, non-deterministic
  across runs, can contain factual errors, and does not constitute
  radiological interpretation.
- The FastSurfer wrapper currently expects input T1w files to match the
  pattern `t1_3d_*.nii.gz`. Non-matching filenames must be renamed manually
  before invocation. Planned for v0.2.
- Installation friction documented in [`CONTRIBUTING.md`](CONTRIBUTING.md):
  `RecursionError` observed during `pip install` in some venv configurations;
  TLS inspection by antivirus software (notably Avast on Windows) may require
  a `truststore` workaround for HTTPS downloads.
- This pipeline has been executed end-to-end on only one external healthy
  subject (see Validation). It has not been evaluated on a cohort, has not
  been benchmarked against reference quantification tools, and has no
  formal clinical validation.

[Unreleased]: https://github.com/lindsay-barret/neuro-analyzer/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/lindsay-barret/neuro-analyzer/releases/tag/v0.1.0
