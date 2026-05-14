"""Single source of truth for the bilingual ES/EN medical disclaimer.

The text below is the canonical block prescribed by CLAUDE.md section 3.
Any user-facing entry point (CLI ``--help``, generated report header,
package docstring) must display it.

This module is the single source for runtime use — call sites that emit
the disclaimer at runtime MUST import ``DISCLAIMER_BILINGUAL`` from here
rather than duplicating the text.

Two locations duplicate the text verbatim because Python docstrings are
static and cannot be assembled from imports:

  * ``neuro_analyzer/__init__.py`` — package docstring
  * ``neuro_analyzer/main.py`` — docstring of the ``cli()`` Click group
    (Click reads it statically to render ``--help``)

If the canonical text changes, those two docstrings must be updated in
sync. The disclaimer presence tests in ``tests/test_disclaimer.py``
catch drift by asserting both ES and EN anchors at every emission site.
"""

DISCLAIMER_BILINGUAL = (
    "ESTA HERRAMIENTA ES PARA INVESTIGACIÓN Y EDUCACIÓN ÚNICAMENTE.\n"
    "NO ESTÁ APROBADA POR COFEPRIS, FDA, EMA NI NINGUNA AUTORIDAD SANITARIA.\n"
    "NO DEBE UTILIZARSE PARA DIAGNÓSTICO, TRATAMIENTO O TOMA DE DECISIONES CLÍNICAS.\n"
    "\n"
    "THIS TOOL IS FOR RESEARCH AND EDUCATIONAL PURPOSES ONLY.\n"
    "NOT APPROVED BY ANY REGULATORY AUTHORITY (FDA, EMA, COFEPRIS, ETC.).\n"
    "NOT INTENDED FOR CLINICAL DIAGNOSIS OR TREATMENT DECISIONS."
)


def as_markdown_blockquote() -> str:
    """Return the disclaimer formatted as a Markdown blockquote.

    Each line is prefixed with ``> `` so the block renders as a single
    quoted section in report headers.
    """
    return "\n".join(f"> {line}" if line else ">" for line in DISCLAIMER_BILINGUAL.splitlines())
