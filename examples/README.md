# Examples

This directory contains illustrative templates. **None of the files here
describe a real patient.** Real cases must stay on your local machine —
the project's `.gitignore` blocks files matching `*-context.yaml`,
`patient-context.*`, and similar so they cannot be committed by accident.

## `example-context.yaml`

A template for the optional patient-context file. Pass it to any pipeline
command with `--context-file` (or via the `PATIENT_CONTEXT_FILE`
environment variable):

```bash
neuro-analyzer scan /path/to/dicom --context-file my-case-context.yaml
neuro-analyzer analyze /path/to/slices --context-file my-case-context.yaml
neuro-analyzer report  /path/to/analysis --context-file my-case-context.yaml
neuro-analyzer quantify /path/to/nifti  --context-file my-case-context.yaml
```

### What the file controls

| Field | Used by | Effect |
|---|---|---|
| `report_title` | `report_generator` | H1 of the qualitative report. |
| `patient_context` | Vision prompt + quantitative report header | Free-form de-identified clinical block. |
| `diagnostic_focus` | Vision prompt | What the model should look for. Keep neutral — see "Cognitive bias" below. |
| `sequence_specific_notes.{swi,flair,t1,...}` | Vision prompt | Per-sequence overrides on top of `diagnostic_focus`. |
| `clinical_correlation.{eeg,development,...}` | Qualitative report (section 7) | Free-form prose subsections. Omitted entries are skipped, not blanked. |

### Cognitive bias note

Hardcoding a suspected diagnosis in the prompt biases the model toward
confirming it. The example file deliberately uses neutral phrasing
(*"signale ce que tu observes, pas ce que tu attends"*) and the
fallback used when no context is provided is also unbiased. If you
*do* have a working diagnostic hypothesis, prefer phrasing it as a
focus area or differential to evaluate, rather than a presumption.

### Running without a context file

The pipeline runs end-to-end without `--context-file`. In that mode
the Vision prompt uses generic fallbacks, the quantitative report
header shows only the generation date, and section 7 of the
qualitative report is omitted. This is the right starting point when
exploring a new dataset.

## Adding example data

A future release will link to a public pediatric MRI dataset (e.g. on
OpenNeuro) that can be used to exercise the pipeline end-to-end. For
now, generate a synthetic NIfTI with `numpy` + `nibabel` if you want
to smoke-test the install without real DICOMs.
