# External Validation Summary

> **Medical disclaimer reminder.** This tool is for research and educational
> purposes only, not approved by any regulatory authority, not intended for
> clinical diagnosis or treatment decisions. See [`DISCLAIMER.md`](../DISCLAIMER.md)
> for full terms.

## Purpose

This document summarizes the external validation effort performed prior to
the v0.1.0 public release of `neuro-analyzer`. The goal was to verify that
the pipeline produces plausible quantitative output on at least one healthy
pediatric subject obtained from a public dataset, independent of the
single clinical case that originally motivated the project.

This validation is intentionally minimal. It does **not** constitute
clinical validation, cohort validation, or evidence of diagnostic utility.
It is a basic functional check: "the pipeline runs end-to-end on
publicly-available data and produces anatomically plausible volumes on a
healthy control."

## Methodology

Three pediatric T1-weighted scans (ages 7–9) from public OpenNeuro
datasets were processed through the pipeline. For each subject, the
following were recorded:

- Brainmask volume (post-skull-strip)
- Number of non-zero anatomical regions in `aseg+DKT.stats`
- Subcortical structure volumes (Thalamus, Putamen, Pallidum, Hippocampus,
  Amygdala, Caudate, Brain-Stem) bilateral
- Output of the structural completeness QC checks (see
  [`limitations.md`](limitations.md))

To isolate responsibility between the pipeline wrapper and the underlying
FastSurfer container, two of the three subjects were also processed
through the official `deepmi/fastsurfer:latest` container directly,
bypassing the wrapper.

## Results

### Successful validation: sub-pixar066 (ds000228, PIXAR / Saxe lab MIT)

| Metric | Value |
|---|---|
| Subject | sub-pixar066, 7.0 years, female |
| Dataset | [ds000228](https://openneuro.org/datasets/ds000228) (Richardson et al., Saxe lab MIT) |
| Defacing | pyDeface (OpenNeuro standard) |
| Brainmask volume | 1562 cm³ |
| BrainSegVol | 1311 cm³ |
| Non-zero regions | 95 / 100 |
| QC verdict | **Pass** |

Bilateral subcortical volumes (mm³, L/R, asymmetry ratio):

- Thalamus: 8779 / 8300 (1.06)
- Putamen: 5880 / 5997 (1.02)
- Pallidum: 2255 / 2092 (1.08)
- Hippocampus: 4536 / 4679 (1.03)
- Amygdala: 1794 / 1943 (1.08)
- Caudate: 4635 / 4920 (1.06)
- Brain-Stem: 20148

All asymmetry ratios are within biological range. All required subcortical
structures are present with plausible volumes for a 7-year-old. No
corruption warnings, no QC failures.

### Failure characterization: sub-5005 and sub-5007 (ds003604)

Two subjects from [ds003604](https://openneuro.org/datasets/ds003604)
(Wang/Lytle/Booth, Vanderbilt University) were processed before
sub-pixar066. Both produced segmentations that the structural completeness
QC checks now flag as failed:

| Subject | Brainmask | Failure mode |
|---|---|---|
| sub-5005, ses-9 | 552 cm³ (vs ~1400 expected) | Catastrophic — FastSurfer corruption warning fired, brainmask ~40% of expected, only 39/100 regions non-zero, criteria 1+2+3 all triggered |
| sub-5007, ses-9 | 1484 cm³ (plausible) | Multi-criterion partial — Pallidum L/R = 0, Putamen L = 0, Brain-Stem = 0, Putamen R = 85 mm³, Amygdala L = 95 mm³, Thalamus L/R = 847/159 mm³ (5.3:1) |

Importantly, sub-5007 was a **silent failure** before the QC tightening:
the FastSurfer-internal corruption warning did not fire, the brainmask
volume looked plausible, and a quantitative report was generated as if the
output were valid. The structural completeness checks introduced in
release v0.1.0 catch this case.

## Root cause analysis

The failure on ds003604 is **not** a bug in the `neuro-analyzer` wrapper.
The official `deepmi/fastsurfer:latest` container, run directly on
sub-5007 with the same input, produced **bit-identical volumes** to those
of the wrapper. The hypothesis that the wrapper's invocation flags or
preprocessing were the cause was thereby falsified empirically.

The failure is **not** a general limitation of FastSurfer in pediatric
subjects either. Zughayyar et al. (2025) report a 2.7% segmentation
failure rate on a multicenter cohort of 448 pediatric subjects (4–18
years) using the same FastSurfer `seg_only` mode. The two consecutive
ds003604 subjects we processed both failed, which is well outside this
published base rate. We do not present a formal hypothesis test on
N = 2: the selection was not pre-registered (sub-5007 was retried
after sub-5005 failed catastrophically), and a sample of two cannot
support a frequentist conclusion. The point is qualitative — failure
on this dataset is sufficiently far from expected that further
investigation was warranted, not that the difference is statistically
established.

The failure is **not** caused by the local Docker / Windows setup or by
defacing in general. The PIXAR control subject (sub-pixar066) uses
pyDeface OpenNeuro standard defacing and processes successfully on the
same setup.

The remaining hypothesis, narrowed by elimination, is **specificity to
ds003604**. Two non-mutually-exclusive candidates:

1. A defacing procedure specific to the Booth lab. Note: ds003604's
   own dataset description does not cite a defacing reference. The
   inference that it uses an in-house Booth-lab procedure rests on the
   sister dataset ds002424 (also Booth lab) explicitly citing Lytle,
   McNorgan, & Booth (2019) as its defacing reference. We have not
   directly verified that ds003604 uses the same procedure.
2. Acquisition characteristics specific to the Vanderbilt Booth lab
   (scanner, protocol, subject population overlap).

Disambiguating between these would require either a non-Booth dataset
using the same custom defacing (no known public source), or non-defaced
ds003604 (not permitted by OpenNeuro). This disambiguation is **out of
scope** for v0.1.0 and is not a prerequisite for the public release:
the failure mode is input-specific, not tool-specific, and it is caught
reliably by the QC checks shipped with v0.1.0.

## Quality control instrumentation

The structural completeness QC introduced in v0.1.0 detects three classes
of segmentation failure that the FastSurfer-internal corruption check
alone does not catch:

1. **Required subcortical structures with zero volume** (criterion 1)
2. **Required subcortical structures below a noise floor of 100 mm³** (criterion 2)
3. **Lateralized failure detected via L/R asymmetry ratio greater than 3:1** (criterion 3)

When any criterion is triggered, the pipeline raises
`SegmentationCorruptedError` with exit code 3 and a bilingual ES/EN error
message. No quantitative report is produced. See
[`limitations.md`](limitations.md) for further details on the QC
philosophy and known gaps.

## Implications for users

Users running this pipeline should expect:

- **The pipeline functions on standard public pediatric data** (PIXAR
  ds000228 verified). Results on similar OpenNeuro datasets are likely
  to be comparable to those of FastSurfer in standalone use.
- **Some inputs will fail the QC checks** even when the FastSurfer
  internal segmentation reports no error. This is the intended behavior
  and indicates that quantitative output cannot be trusted on that input.
- **A pass on the QC checks is not a guarantee of clinical validity.**
  The QC catches catastrophic and gross-partial segmentation failures;
  it does not validate against age-matched normative atlases, does not
  detect subtle malsegmentations, and does not replace visual inspection
  by a qualified neuroradiologist.

Visual inspection of FastSurfer outputs is recommended for any
quantitative use of this pipeline, in line with the recommendation made
by Zughayyar et al. (2025) for FastSurfer in general.

## Reproducing this validation

Download sub-pixar066 from ds000228 (OpenNeuro public S3, no credentials):

```bash
mkdir -p validation_data/ds000228/sub-pixar066
aws s3 cp --no-sign-request \
  s3://openneuro.org/ds000228/sub-pixar066/anat/sub-pixar066_T1w.nii.gz \
  validation_data/ds000228/sub-pixar066/
```

The `quantify` command resolves its T1 input by globbing `t1_3d*.nii.gz`
inside the directory passed as argument, so the OpenNeuro file must be
renamed (or symlinked):

```bash
cd validation_data/ds000228/sub-pixar066
mv sub-pixar066_T1w.nii.gz t1_3d_sub-pixar066.nii.gz
cd -
```

Run the quantitative pass (requires Docker for the FastSurfer container,
pulled automatically on first run):

```bash
neuro-analyzer quantify validation_data/ds000228/sub-pixar066 \
  --subject-id sub-pixar066 \
  --threads 8
```

Expected output:

- FastSurfer container completes in ~15–20 min on a modern CPU
- Brainmask volume in the 1500–1600 cm³ range
- ~95/100 non-zero regions in `aseg+DKT.stats`
- Structural-completeness QC passes; the pipeline proceeds to generate
  the quantitative report
- A `quantitative_report.md` is written next to the input directory

A failure (any of the three QC criteria triggered) raises
`SegmentationCorruptedError` with exit code 3 and produces no report;
this is the intended behavior on out-of-distribution inputs and is
**not** a reproducibility failure of this validation.

## References

- Zughayyar I, Bauer M, Güttler C, et al. *A FastSurfer Database for
  Age-Specific Brain Volumes in Healthy Children: A Tool for Quantifying
  Localized and Global Brain Volume Alterations in Pediatric Patients.*
  Brain and Behavior. 2025;15(7):e70689. doi:10.1002/brb3.70689
- Henschel L, Conjeti S, Estrada S, Diers K, Fischl B, Reuter M.
  *FastSurfer — A fast and accurate deep learning based neuroimaging
  pipeline.* NeuroImage. 2020;219:117012.
  doi:10.1016/j.neuroimage.2020.117012
- Richardson H, Lisandrelli G, Riobueno-Naylor A, Saxe R.
  *Development of the social brain from age three to twelve years.*
  Nature Communications. 2018;9:1027.
  doi:10.1038/s41467-018-03399-2 (ds000228)
- Wang J, Lytle MN, Weiss Y, Yamasaki BL, Booth JR.
  *A longitudinal neuroimaging dataset on language processing in
  children ages 5, 7, and 9 years old.* Scientific Data. 2022;9.
  doi:10.1038/s41597-021-01106-3 (ds003604)
- Lytle MN, McNorgan C, Booth JR.
  *A longitudinal neuroimaging dataset on multisensory lexical
  processing in school-aged children.* Scientific Data. 2019;6.
  doi:10.1038/s41597-019-0338-5
  (Booth-lab defacing reference, cited explicitly by ds002424; the
  procedure used in ds003604 is not directly documented but is
  inferred to be the same in-house pipeline.)
