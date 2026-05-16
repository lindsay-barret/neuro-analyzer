# neuro-analyzer

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20222509.svg)](https://doi.org/10.5281/zenodo.20222509)

> ## ⚠️ AVISO MÉDICO / MEDICAL DISCLAIMER
>
> **ESTA HERRAMIENTA ES PARA INVESTIGACIÓN Y EDUCACIÓN ÚNICAMENTE.**
> NO ESTÁ APROBADA POR COFEPRIS, FDA, EMA NI NINGUNA AUTORIDAD SANITARIA.
> NO DEBE UTILIZARSE PARA DIAGNÓSTICO, TRATAMIENTO O TOMA DE DECISIONES CLÍNICAS.
> Las decisiones médicas deben basarse en evaluación clínica especializada
> y herramientas con registro sanitario apropiado.
>
> **THIS TOOL IS FOR RESEARCH AND EDUCATIONAL PURPOSES ONLY.**
> Not approved by any regulatory authority (FDA, EMA, COFEPRIS, etc.).
> Not intended for clinical diagnosis, treatment, or medical decision-making.
> Always consult qualified medical professionals using regulatory-approved tools.

---

## 🇪🇸 Español

### ¿Qué es?

`neuro-analyzer` es un pipeline reproducible para el reanálisis cuantitativo de IRM cerebrales pediátricas estructurales. Orquesta herramientas establecidas de neuroimagen (FastSurfer, dcm2niix, nibabel) y genera un reporte cuantitativo (volumetría regional con Z-scores, índice de girificación local opcional, análisis visual asistido) destinado a contextos de **investigación, educación y discusión clínica con especialistas**.

El proyecto nació de un caso pediátrico real donde un reanálisis cuantitativo cuatro años después de la IRM original modificó significativamente la caracterización diagnóstica de una malformación del desarrollo cortical, con implicaciones concretas en el manejo terapéutico.

### Lo que NO es

- **No es un dispositivo médico aprobado.** No reemplaza la evaluación radiológica ni neurológica.
- **No tiene validación clínica formal.** Está basado en un caso de uso individual; no ha sido evaluado en cohortes.
- **No genera diagnósticos.** Genera mediciones cuantitativas y descripciones estructurales que requieren interpretación por un especialista.

### Audiencia objetivo

- Investigadores en neuroimagen pediátrica
- Educadores que enseñan análisis de IRM
- Padres con formación técnica que desean comprender mejor estudios de sus hijos (siempre en complemento, nunca en reemplazo, de la evaluación médica)
- Desarrolladores que quieren extender el pipeline

### Pipeline

```
DICOM → conversión NIfTI (dcm2niix) → segmentación + volumetría (FastSurfer)
       → análisis visual asistido (Claude Vision API) → reporte cuantitativo
```

Funcionalidades opcionales que requieren FreeSurfer (instalación independiente con licencia académica del usuario):
- Local Gyrification Index (LGI)

### Instalación rápida (Docker recomendado)

```bash
git clone https://github.com/lindsay-barret/neuro-analyzer.git
cd neuro-analyzer
cp .env.example .env  # editar y agregar ANTHROPIC_API_KEY
docker compose up --build
```

Ver [`docs/installation.md`](docs/installation.md) para instalación nativa y [`docs/usage.md`](docs/usage.md) para ejemplos.

### Ejemplo reproducible

Un ejemplo end-to-end usando un dataset público de OpenNeuro está disponible en [`examples/`](examples/). Ver [`examples/README.md`](examples/README.md) para instrucciones.

### Limitaciones conocidas

Documentadas honestamente en [`docs/limitations.md`](docs/limitations.md). Resumen:

- FastSurfer puede fallar en cortezas severamente malformadas (paradójicamente útil como confirmación indirecta de severidad, pero no diseñado para esto)
- La precisión volumétrica depende de la calidad del scanner, protocolo, y movimiento del paciente
- Los Z-scores se calculan contra atlas adultos por defecto; para pediatría se recomienda atlas específicos (en desarrollo)
- El análisis visual asistido por LLM es probabilístico y no reemplaza interpretación radiológica

### Mantenimiento y ciclo de vida del proyecto

Este proyecto está mantenido activamente hasta **diciembre de 2027**.
Después de esa fecha, el repositorio será archivado tal cual:

- El código permanecerá públicamente accesible y citable mediante su DOI Zenodo
- No se realizarán más correcciones de errores, parches de seguridad, ni
  evoluciones funcionales por parte de la mantenedora
- Los issues y pull requests no serán revisados después del archivo
- Se anima a hacer forks para continuar el desarrollo de forma independiente

Esta fecha de fin de mantenimiento es una decisión deliberada para mantener
honesto el alcance del proyecto y evitar la deriva hacia un "producto"
sin recursos para sostenerlo.

### Cómo citar

Si este software te resulta útil, por favor cita:

```
[Citación pendiente al primer release Zenodo]
```

Ver [`CITATION.cff`](CITATION.cff) para metadatos completos.

### Licencia

MIT — ver [`LICENSE`](LICENSE).

Las dependencias mantienen sus propias licencias:
- FastSurfer (Apache 2.0)
- dcm2niix (BSD)
- nibabel (MIT)
- FreeSurfer (académica, no distribuida con este proyecto, instalación independiente)

### Contribuir

Ver [`CONTRIBUTING.md`](CONTRIBUTING.md). Issues y PRs bienvenidos.

### Contacto

Para preguntas científicas o colaboraciones:
- [Abrir un issue](../../issues) en este repositorio (preferido para preguntas técnicas)
- Email: `lindsay.barret.research@gmail.com` (para colaboraciones, prensa, consultas formales)
- ORCID: [0009-0004-7411-3240](https://orcid.org/0009-0004-7411-3240)

---

## 🇬🇧 English

### What is it?

`neuro-analyzer` is a reproducible pipeline for quantitative re-analysis of pediatric structural brain MRI. It orchestrates established neuroimaging tools (FastSurfer, dcm2niix, nibabel) and produces a quantitative report (regional volumetry with Z-scores, optional local gyrification index, AI-assisted visual analysis) intended for **research, education, and clinical discussion with specialists**.

The project originated from a real pediatric case where quantitative re-analysis four years after the original MRI significantly modified the diagnostic characterization of a cortical development malformation, with concrete therapeutic management implications.

### What it is NOT

- **Not an approved medical device.** Does not replace radiological or neurological evaluation.
- **No formal clinical validation.** Based on an individual use case; not evaluated in cohorts.
- **Does not produce diagnoses.** Produces quantitative measurements and structural descriptions requiring specialist interpretation.

### Target audience

- Pediatric neuroimaging researchers
- Educators teaching MRI analysis
- Technically-skilled parents seeking better understanding of their children's studies (always as complement, never replacement, of medical evaluation)
- Developers extending the pipeline

### Pipeline

```
DICOM → NIfTI conversion (dcm2niix) → segmentation + volumetry (FastSurfer)
       → AI-assisted visual analysis (Claude Vision API) → quantitative report
```

Optional features requiring FreeSurfer (independent installation with user's academic license):
- Local Gyrification Index (LGI)

### Quick install (Docker recommended)

```bash
git clone https://github.com/lindsay-barret/neuro-analyzer.git
cd neuro-analyzer
cp .env.example .env  # edit and add ANTHROPIC_API_KEY
docker compose up --build
```

See [`docs/installation.md`](docs/installation.md) for native install and [`docs/usage.md`](docs/usage.md) for examples.

### Reproducible example

An end-to-end example using a public OpenNeuro dataset is available in [`examples/`](examples/). See [`examples/README.md`](examples/README.md) for instructions.

### Known limitations

Documented honestly in [`docs/limitations.md`](docs/limitations.md). Summary:

- FastSurfer can fail on severely malformed cortex (paradoxically useful as indirect severity confirmation, but not designed for this)
- Volumetric accuracy depends on scanner quality, protocol, and patient motion
- Z-scores computed against adult atlases by default; pediatric-specific atlases recommended (in development)
- LLM-assisted visual analysis is probabilistic and does not replace radiological interpretation

### Project maintenance and lifecycle

This project is actively maintained until **December 2027**.
After that date, the repository will be archived as-is:

- The code will remain publicly accessible and citable via its Zenodo DOI
- No further bug fixes, security patches, or feature work will be performed
  by the maintainer
- Issues and pull requests will not be reviewed after archiving
- Forks are encouraged for continued independent development

This end-of-maintenance date is a deliberate decision to keep the project's
scope honest and avoid drift toward a "product" without resources to sustain it.

### How to cite

If you find this software useful, please cite:

```
[Citation pending first Zenodo release]
```

See [`CITATION.cff`](CITATION.cff) for full metadata.

### License

MIT — see [`LICENSE`](LICENSE).

Dependencies retain their own licenses:
- FastSurfer (Apache 2.0)
- dcm2niix (BSD)
- nibabel (MIT)
- FreeSurfer (academic, not distributed with this project, install separately)

### Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Issues and PRs welcome.

### Contact

For scientific questions or collaborations:
- [Open an issue](../../issues) in this repository (preferred for technical questions)
- Email: `lindsay.barret.research@gmail.com` (for collaborations, press, formal inquiries)
- ORCID: [0009-0004-7411-3240](https://orcid.org/0009-0004-7411-3240)

---

## Acknowledgments

This project builds on the work of:
- [FastSurfer](https://github.com/Deep-MI/FastSurfer) — Henschel et al., NeuroImage 2020
- [dcm2niix](https://github.com/rordenlab/dcm2niix) — Li et al., J Neurosci Methods 2016
- [nibabel](https://nipy.org/nibabel/)
- [FreeSurfer](https://surfer.nmr.mgh.harvard.edu/) — Fischl, NeuroImage 2012 (used optionally)
- [Anthropic Claude](https://www.anthropic.com/) — for AI-assisted visual analysis
