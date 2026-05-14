# CLAUDE.md — neuro-analyzer

This file provides project context to Claude Code (and other AI coding
assistants) working in this repository. It is intentionally committed so
that contributors who use AI tools start with the same baseline.

## What this project is

`neuro-analyzer` is a Python pipeline that orchestrates quantitative
re-analysis of pediatric structural brain MRI. It chains together
established neuroimaging tools and produces a quantitative report
(regional volumetry with Z-scores, optional local gyrification index,
AI-assisted visual analysis).

```
DICOM → pydicom → dcm2niix → FastSurfer (segmentation, volumetry, thickness)
       → [optional FreeSurfer for LGI] → nibabel/matplotlib (visualization)
       → Claude Vision API (visual analysis) → quantitative report
```

What has value here is the orchestration, the prompts for visual
analysis, the report format, and the explicit "research/education only"
philosophy. The underlying tools (FastSurfer, FreeSurfer, dcm2niix,
nibabel, Anthropic Claude) are third-party dependencies and are credited
as such — the project does not claim ownership of their work.

## What this project is NOT

- Not a medical device
- Not approved by any regulatory authority
- Not clinically validated in cohorts
- Not a diagnostic tool

See `DISCLAIMER.md` for the full medical-regulatory notice. Every user-
facing entry point (README, CLI `--help`, generated report header) must
display the short bilingual disclaimer.

## Hard constraints (non-negotiable)

### 1. No patient data in the public repo, ever

No DICOM, no NIfTI, no generated report, no log containing identifying
paths, no patient name. This includes:

- No file in the repo containing real patient names or identifiers
- No hardcoded paths like `C:\Users\<name>\<patient>_<study>` in code,
  comments, tests, or examples
- No real report output committed, even if "anonymized"
- No screenshot of a real MRI in the documentation

For documentation and tests:
- Point to public OpenNeuro datasets, do not redistribute them
- For unit tests, generate small synthetic NIfTI volumes with
  `numpy.random` + `nibabel.Nifti1Image`
- For example clinical context, use the fictional case in
  `examples/example-context.yaml` only

### 2. FreeSurfer cannot be redistributed

The FreeSurfer license forbids redistribution and commercial use, and
requires each user to obtain their own academic license. Therefore:

- The public Dockerfile MUST NOT include FreeSurfer or download
  FreeSurfer binaries
- The default pipeline MUST work without FreeSurfer (FastSurfer
  standalone for volumetry, thickness, segmentation)
- FreeSurfer-dependent features (LGI in particular) live in
  `optional/freesurfer_lgi.py` with a clear docstring telling users to
  install FreeSurfer independently with their own license
- No `freesurfer/license.txt` is ever committed

### 3. Medical disclaimer is omnipresent

Every user entry point (README, CLI `--help`, generated report header,
main module docstring) MUST display:

```
ESTA HERRAMIENTA ES PARA INVESTIGACIÓN Y EDUCACIÓN ÚNICAMENTE.
NO ESTÁ APROBADA POR COFEPRIS, FDA, EMA NI NINGUNA AUTORIDAD SANITARIA.
NO DEBE UTILIZARSE PARA DIAGNÓSTICO, TRATAMIENTO O TOMA DE DECISIONES CLÍNICAS.

THIS TOOL IS FOR RESEARCH AND EDUCATIONAL PURPOSES ONLY.
NOT APPROVED BY ANY REGULATORY AUTHORITY (FDA, EMA, COFEPRIS, ETC.).
NOT INTENDED FOR CLINICAL DIAGNOSIS OR TREATMENT DECISIONS.
```

### 4. No secrets in the repo

`ANTHROPIC_API_KEY` and any other credential is read from environment
variables only. `.env` is in `.gitignore`. `.env.example` provides
empty templates. Run `gitleaks detect` before pushing anything.

### 5. Patient context is external and parameterized

Real clinical context is never hardcoded. The pipeline reads context
from a YAML file passed via `--context-file` or the
`PATIENT_CONTEXT_FILE` environment variable. The published example
(`examples/example-context.yaml`) is a fully fictional case for
documentation purposes. All `*-context.yaml` files except this one are
gitignored.

## Design principles

- **Anti-perfectionism.** Publish early, imperfect, dated. Iterate after.
  An imperfect public v0.1 beats six months of private polishing.
- **Reproducibility.** Docker is the recommended primary install method.
  `requirements.txt` is pinned with exact versions.
- **Minimum viable documentation.** Clear README, one end-to-end example
  that works against a public OpenNeuro dataset, that's enough for v0.1.
- **Bilingual ES/EN README.** Spanish primary (LATAM audience,
  underserved in pediatric neuroimaging tooling), English equivalent.
  Code and docstrings stay in English (open-source standard).
- **Cite the tools you use.** FastSurfer, dcm2niix, nibabel, Anthropic
  Claude, FreeSurfer when applicable — all cited explicitly in README
  and in the generated report.

## Repo structure

```
neuro-analyzer-public/
├── CLAUDE.md                  # this file
├── README.md                  # bilingual ES/EN, disclaimer at top
├── LICENSE                    # MIT
├── DISCLAIMER.md              # full medical disclaimer
├── CITATION.cff               # for Zenodo, citable
├── CONTRIBUTING.md            # contribution guidelines + scope rules
├── CHANGELOG.md
├── .gitignore                 # robust, blocks patient data + secrets
├── .env.example
├── requirements.txt
├── setup.py
├── src/
│   └── neuro_analyzer/        # main package
├── examples/
│   ├── example-context.yaml   # fictional case for documentation
│   └── ...
└── templates/                 # report templates
```

Targets that may not yet exist (added incrementally as the project
matures):

- `docker/Dockerfile` (without FreeSurfer)
- `tests/` with smoke + synthetic-volume tests
- `.github/workflows/ci.yml` for CI
- `optional/freesurfer_lgi.py` for the LGI module

## Scope discipline

`CONTRIBUTING.md` defines an explicit "Out of scope" list of
contributions that will be rejected on principle (clinical positioning,
disclaimer weakening, FreeSurfer bundling, patient-identifiable data).
This is not flexibility, it is policy.

In-scope contributions: bug fixes, error handling for malformed cortex
edge cases, doc improvements (especially translations), additional
public dataset examples, performance, additional malformations of
cortical development, pediatric atlas integration, FastSurfer error
recovery.

## Working with the maintainer

The maintainer (Lindsay) prefers:

- French as working language for direct communication; project artifacts
  (code, docstrings, commits, public docs) stay in English
- Direct, factual feedback over politeness
- Blind-spot calls and honest critique even when not requested
- Web search and source citation when uncertain
- Pushback on weak ideas rather than accommodation

This is a one-person project with a defined sunset (see SLA in README).
Do not expand scope without explicit agreement.

## Action gates

Always ask before:

- Any destructive git operation (`filter-repo`, `push --force`, history
  rebase)
- The first push to any public remote
- Creating a release tag (irreversible once Zenodo archives it)
- Any change that could affect the license or regulatory positioning

Do not ask for:

- Standard Python implementation choices
- The repo structure described above
- Drafting docs, tests, or refactors that fit the design principles
- Local commits during development
