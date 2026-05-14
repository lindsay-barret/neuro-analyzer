"""Slice analysis via the Claude Vision API."""

import base64
import json
import logging
import time
from pathlib import Path

import anthropic

from .config import (
    API_MODEL, API_MAX_TOKENS, API_MAX_RETRIES, API_RETRY_BACKOFF,
    DEFAULT_DIAGNOSTIC_FOCUS, DEFAULT_SEQUENCE_NOTES,
)
from .slice_selector import SliceSelection

logger = logging.getLogger(__name__)


def _build_prompt(selection: SliceSelection, context: dict | None = None) -> str:
    """Build the per-slice Vision prompt.

    The prompt is parameterized via the optional ``context`` mapping (loaded
    from a user-supplied YAML — see ``config.load_patient_context``) so that
    no diagnostic suspicion is hardcoded at the repository level.

    Cognitive-bias rationale: hardcoding diagnostic suspicions in the Vision
    prompt biases the model toward confirming the suspected pathology.
    Keeping it parameterizable forces explicit user intent — and when no
    context is provided, the model is instructed to observe freely without
    presupposing any diagnosis.

    Args:
        selection: SliceSelection describing which slice is being analyzed.
        context: Optional dict with keys ``patient_context`` (free-form
            anonymized clinical context block) ``diagnostic_focus``
            (free-form prose telling the model what the user is looking
            for), and ``sequence_specific_notes`` (dict keyed by sequence
            name, e.g. ``swi``). Missing keys fall back to neutral defaults.

    Returns:
        The full prompt string sent to the Vision API.
    """
    context = context or {}

    patient_context_block = (context.get("patient_context") or "").strip()
    diagnostic_focus = (
        (context.get("diagnostic_focus") or "").strip()
        or DEFAULT_DIAGNOSTIC_FOCUS
    )

    sections = [
        "You are an experienced pediatric neuroradiologist.",
    ]

    if patient_context_block:
        sections.append(f"CONTEXT:\n{patient_context_block}")

    sections.append(
        f"SLICE PRESENTED:\n"
        f"- Sequence: {selection.sequence.upper()}\n"
        f"- Plane: {selection.plane}\n"
        f"- Estimated anatomical level: {selection.anatomical_level}\n"
        f"- Slice index: {selection.slice_index}\n"
        f"- Position (fraction of volume): {selection.position_fraction:.2f}"
    )

    sections.append(f"INSTRUCTIONS:\n{diagnostic_focus}")

    # Per-sequence notes: user-provided override defaults; defaults override
    # silence. Missing entries fall through cleanly.
    user_notes = context.get("sequence_specific_notes") or {}
    seq_key = selection.sequence.lower()
    note = None
    for k in (seq_key, seq_key.split("_")[0]):
        if k in user_notes and user_notes[k]:
            note = str(user_notes[k]).strip()
            break
    if note is None:
        for k in (seq_key, seq_key.split("_")[0]):
            if k in DEFAULT_SEQUENCE_NOTES:
                note = DEFAULT_SEQUENCE_NOTES[k]
                break
    if note:
        sections.append(f"SEQUENCE-SPECIFIC NOTE ({selection.sequence.upper()}):\n{note}")

    sections.append(
        "Reply ONLY with valid JSON (no text before or after), "
        "with this exact structure:\n"
        "{\n"
        f'  "slice_id": "{selection.sequence}_{selection.plane}_{selection.slice_index:04d}",\n'
        f'  "plane": "{selection.plane}",\n'
        '  "anatomical_level": "precise description of the visible anatomical level",\n'
        '  "image_quality": "good|adequate|poor|non_diagnostic",\n'
        '  "observations": {\n'
        '    "cortical_thickness": {\n'
        '      "description": "description of the observed cortical thickness",\n'
        '      "abnormal_regions": ["list of abnormal regions"],\n'
        '      "severity": "normal|mild|moderate|severe",\n'
        '      "laterality": "bilateral|right_predominant|left_predominant|unilateral_right|unilateral_left|normal"\n'
        '    },\n'
        '    "gyrification": {\n'
        '      "description": "description of the gyrification pattern",\n'
        '      "pattern": "normal|pachygyric|polymicrogyric|agyric|mixed",\n'
        '      "affected_regions": ["list of affected regions"]\n'
        '    },\n'
        '    "grey_white_interface": {\n'
        '      "description": "sharpness of the gray matter / white matter interface",\n'
        '      "clarity": "sharp|slightly_blurred|blurred|indistinct",\n'
        '      "abnormal_regions": ["regions where the interface is abnormal"]\n'
        '    },\n'
        '    "asymmetry": {\n'
        '      "present": true,\n'
        '      "description": "description of any right-left asymmetry"\n'
        '    },\n'
        '    "ventricles": {\n'
        '      "description": "appearance of the ventricles if visible",\n'
        '      "abnormality": "normal|dilated|asymmetric|colpocephaly|other"\n'
        '    },\n'
        '    "corpus_callosum": {\n'
        '      "description": "appearance of the corpus callosum if visible",\n'
        '      "abnormality": "normal|thin|dysgenesis|agenesis|not_visible"\n'
        '    },\n'
        '    "additional_findings": [\n'
        '      "any additional abnormality: heterotopia, calcification, vascular abnormality, etc."\n'
        '    ],\n'
        '    "regions_clearly_abnormal": ["list of clearly abnormal regions"],\n'
        '    "regions_clearly_normal": ["list of clearly normal regions"],\n'
        '    "regions_uncertain": ["regions where the assessment is uncertain"]\n'
        '  },\n'
        '  "clinical_relevance": "how this slice relates to the provided clinical picture",\n'
        '  "confidence": "high|moderate|low",\n'
        '  "limitations": "limitations of the interpretation on this slice"\n'
        '}'
    )

    return "\n\n".join(sections)


def analyze_slice(
    image_path: Path,
    selection: SliceSelection,
    client: anthropic.Anthropic,
    model: str = API_MODEL,
    context: dict | None = None,
) -> dict | None:
    """Send a single slice to the Vision API and return its parsed JSON result."""
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    prompt = _build_prompt(selection, context=context)

    for attempt in range(API_MAX_RETRIES):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=API_MAX_TOKENS,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_data,
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
            )

            response_text = response.content[0].text.strip()

            if response_text.startswith("```"):
                response_text = response_text.split("\n", 1)[1]
                if response_text.endswith("```"):
                    response_text = response_text[:-3]
                response_text = response_text.strip()

            result = json.loads(response_text)
            logger.info(f"  ✓ {selection.sequence}_{selection.plane}_{selection.slice_index:04d}")
            return result

        except json.JSONDecodeError as e:
            logger.warning(f"  Invalid JSON (attempt {attempt+1}): {e}")
            logger.debug(f"  Raw response: {response_text[:200]}")
            if attempt == API_MAX_RETRIES - 1:
                return {
                    "slice_id": f"{selection.sequence}_{selection.plane}_{selection.slice_index:04d}",
                    "error": "json_parse_error",
                    "raw_response": response_text[:2000],
                }

        except anthropic.RateLimitError:
            wait = API_RETRY_BACKOFF * (2 ** attempt)
            logger.warning(f"  Rate limit — waiting {wait}s...")
            time.sleep(wait)

        except anthropic.APIError as e:
            logger.error(f"  API error (attempt {attempt+1}): {e}")
            if attempt == API_MAX_RETRIES - 1:
                return {
                    "slice_id": f"{selection.sequence}_{selection.plane}_{selection.slice_index:04d}",
                    "error": str(e),
                }
            time.sleep(API_RETRY_BACKOFF)

        except Exception as e:
            logger.error(f"  Unexpected error: {e}")
            return {
                "slice_id": f"{selection.sequence}_{selection.plane}_{selection.slice_index:04d}",
                "error": str(e),
            }

    return None


def analyze_all_slices(
    slice_results: list[tuple[SliceSelection, Path]],
    output_dir: Path,
    model: str = API_MODEL,
    context: dict | None = None,
) -> list[dict]:
    """Analyse all slices via the Claude API.

    Args:
        slice_results: list of (selection, png_path) from slice_renderer.
        output_dir: directory to save individual JSON results.
        model: Claude model to use.
        context: optional patient/case context (see _build_prompt).

    Returns:
        List of analysis results, one per slice.
    """
    client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY env var

    output_dir.mkdir(parents=True, exist_ok=True)

    all_results = []
    total = len(slice_results)

    logger.info(f"Analyzing {total} slices via {model}...")

    for i, (selection, png_path) in enumerate(slice_results):
        logger.info(f"[{i+1}/{total}] {png_path.name}")

        result_path = output_dir / f"{png_path.stem}.json"
        if result_path.exists():
            try:
                with open(result_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if "error" not in existing:
                    logger.info("  → Already analyzed, skip")
                    all_results.append(existing)
                    continue
            except json.JSONDecodeError:
                pass

        result = analyze_slice(png_path, selection, client, model, context=context)

        if result:
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            all_results.append(result)

        if i < total - 1:
            time.sleep(0.5)

    logger.info(f"Analysis complete: {len(all_results)}/{total} slices analyzed")
    return all_results
