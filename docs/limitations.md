# Known limitations

> Research and educational use only. Not a medical device. Not intended
> for clinical diagnosis or treatment decisions.

This document tracks limitations discovered through use. It is updated
as new failure modes are encountered. The list is not exhaustive — the
absence of an item here does not imply the absence of the failure mode.

## FastSurfer segmentation may silently fail on out-of-distribution inputs

FastSurfer's CNN was trained predominantly on adult T1 acquisitions. On
inputs that fall outside its training distribution, the segmentation
can produce a structurally broken output (e.g. missing all deep
subcortical structures: hippocampus, amygdala, thalamus, basal ganglia,
brainstem, corpus callosum) while still returning exit code 0.

When this happens, FastSurfer emits an internal QC warning in
`<subject>/scripts/deep-seg.log`:

```
[WARNING: run_prediction.py: ...]: Total segmentation volume is too small.
                                    Segmentation may be corrupted.
```

neuro-analyzer reads this log after each segmentation and aborts with
exit code 3 (`SegmentationCorruptedError`) when the warning fires or
when any of the critical merged labels (deep subcortical, ventricles,
cerebellum WM, corpus callosum) are missing.

This check is defensive: it tells you the segmentation failed, not
that it succeeded. A passing check means no failure mode listed here
was detected — it does not certify that the segmentation is
anatomically correct. Visual inspection of the segmentation overlay
remains necessary for any actual use.

Scope of the QC check: in the default seg_only mode (no FreeSurfer
license, no surface reconstruction), the check monitors three
classes of signal:

1. **FastSurfer self-reported corruption** — its internal
   "Total segmentation volume is too small / may be corrupted"
   warning, plus the absence of an entire deep-subcortical or
   ventricular merged label group (10001, 10003).
2. **Structural completeness** — required subcortical structures
   (Pallidum, Putamen, Caudate, Thalamus, Hippocampus, Brain-Stem,
   Amygdala) with zero volume, or with non-zero volume below a
   100 mm³ noise floor. The noise floor is a hard guard, not a
   validation against pediatric norms: a 9-year-old pallidum with
   normative range ~1500-2000 mm³ measured at < 100 mm³ is
   unambiguously a segmentation failure, not biological
   variability. Per-structure age-stratified pediatric norms are
   not yet integrated; that is tracked as a v0.2+ TODO.
3. **Lateralized failure** — L/R asymmetry ratio > 3:1 on paired
   subcortical structures. Pathological hippocampal asymmetry is
   typically 10-15 % (Briellmann 1998, Bien 2005); a 3:1 ratio
   = 200 % asymmetry is far beyond biological range and only
   fires on broken segmentations. If either side is zero the pair
   is skipped here (criterion 1 already caught it).

Cerebellar white matter and corpus callosum labels are excluded
from the check because they are produced by the surface
reconstruction pass and are expected to be absent in seg_only
mode.

This tightening followed the empirical observation that
FastSurfer's seg_only mode can produce partial segmentations that
escape its own internal QC. It aligns with Zughayyar et al.
(*Brain and Behavior* 2025, doi:10.1002/brb3.70689), who reported
a 2.7 % segmentation failure rate on 448 pediatric subjects
(ages 4-18) with FastSurfer in seg_only mode — i.e. a non-trivial
minority of partial failures expected on comparable pediatric
data. Partial segmentations that previously passed silently are
now flagged.

Arbitrage history: this issue was initially scoped as
documentation-only (anti-perfectionism). It was revised after
literature review (Zughayyar 2025) revealed that partial
segmentation is a wrapper-detectable issue rather than a
fundamental limitation that has to be left to manual inspection.

### Confirmed observations

- One case observed: OpenNeuro ds003604 sub-5005, ses-9 (typically
  developing pediatric subject, ~9 yrs). Full segmentation collapse,
  brainmask retained ~552 cm³ vs ~1400 cm³ expected for age, all deep
  subcortical labels missing. Root cause investigation in progress;
  see hypothesized causes below.
- Second case: OpenNeuro ds003604 sub-5007, ses-9 (typically
  developing pediatric subject, ~9 yrs). Different failure mode:
  no FastSurfer corruption warning, total brain mask volume in
  expected range (~1484 cm³), but several subcortical structures
  missing or severely under-segmented. With the structural-
  completeness QC in place, this case is now caught by all three
  criteria simultaneously:
    * Criterion 1 (zero volume): Pallidum L/R, Putamen L, Brain-Stem.
    * Criterion 2 (below 100 mm³ noise floor): Putamen R = 85 mm³,
      Amygdala L = 95.4 mm³.
    * Criterion 3 (L/R ratio > 3:1): Thalamus L = 847 mm³ /
      Thalamus R = 159 mm³ (ratio ≈ 5.3:1).
  Without the structural-completeness checks, this case would have
  passed silently because the FastSurfer log emitted no corruption
  warning and the deep-subcortical merged label was not entirely
  absent.

### Hypothesized causes (not yet confirmed)

These are plausible explanations for the failure mode above. None has
been empirically isolated. They are listed to help users reason about
their own datasets, not as established conclusions.

- Pediatric T1 with high native intensity range (e.g. 3T scans with
  raw `int16` values up to several thousand). The conformation step
  rescales linearly into `uint8 [0, 255]`, which can compress the
  GM/WM contrast outside the range the CNN was trained on.
- Pediatric brain anatomy itself: incomplete myelination, different
  WM/GM ratio, smaller absolute volumes — all under-represented in
  the FastSurfer training set, independent of intensity scaling.
- Aggressive defacing that removes brain tissue near the basal
  surface (less common with the standard pydeface OpenNeuro
  pipeline, but verifiable by visualising the raw NIfTI before
  running FastSurfer).
- Scanner / acquisition protocol drift away from the FastSurfer
  training distribution.

### Recommended mitigation

1. Visually inspect the raw input T1 (orthogonal mid-slices) before
   committing to a multi-hour run.
2. After segmentation completes, visually inspect the segmentation
   overlay regardless of whether the QC check passed.
3. If `SegmentationCorruptedError` fires, do not attempt to interpret
   any partial volumes that may have been produced. Re-run on a
   different subject, or document the failure and stop.
4. neuro-analyzer does not provide a "force-continue" flag. The check
   is strict by design: corrupted segmentations have no clinical or
   research value and silently passing them downstream is worse than
   aborting.

## Other known limitations

- FastSurfer may also fail on severely malformed cortex (paradoxically
  useful as indirect severity confirmation, but not designed for this).
- Volumetric accuracy depends on scanner quality, protocol, and
  patient motion.
- Z-scores are computed against approximate adult-derived norms by
  default; pediatric-specific atlases are recommended (in development).
- LLM-assisted visual analysis is probabilistic and does not replace
  radiological interpretation.

## References

- FastSurfer: Henschel et al., *NeuroImage* 2020,
  doi:10.1016/j.neuroimage.2020.117012.
  Repository: https://github.com/Deep-MI/FastSurfer
- See `CITATION.cff` at the repository root for the full list of
  upstream tools and citations.
