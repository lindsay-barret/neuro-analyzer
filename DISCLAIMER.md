# DISCLAIMER — Medical and Regulatory Notice

## 🇪🇸 Español

### Naturaleza del software

`neuro-analyzer` es una herramienta de software de código abierto destinada exclusivamente a **fines de investigación, educación y aprendizaje**. Genera mediciones cuantitativas y descripciones estructurales a partir de imágenes de resonancia magnética cerebral, mediante la orquestación de herramientas establecidas de neuroimagen y análisis asistido por modelos de lenguaje.

### No es un dispositivo médico

Este software:

- **NO** ha sido aprobado, autorizado, ni registrado por COFEPRIS (México), FDA (EE.UU.), EMA (Unión Europea), ANVISA (Brasil), Health Canada, o cualquier otra autoridad regulatoria sanitaria.
- **NO** cumple con los requisitos de Software como Dispositivo Médico (SaMD) según los marcos del IMDRF, FDA, ni el Reglamento de Insumos para la Salud de México.
- **NO** debe utilizarse para diagnóstico, prevención, monitoreo, tratamiento, o alivio de enfermedades.
- **NO** debe utilizarse como base única o principal para tomar decisiones médicas o terapéuticas.

### Limitaciones inherentes

Los usuarios deben comprender que:

1. **Validación clínica ausente.** El software no ha sido validado en cohortes clínicas. Sus resultados no han sido comparados sistemáticamente contra métodos de referencia.
2. **Errores de procesamiento.** Las herramientas subyacentes (FastSurfer, FreeSurfer cuando aplica) pueden producir errores de segmentación, especialmente en cerebros con malformaciones, lesiones, o anatomía atípica.
3. **Sesgos de los datos de entrenamiento.** Los modelos de segmentación están entrenados predominantemente en cohortes adultas y pueden tener menor precisión en pediatría.
4. **Análisis visual probabilístico.** El análisis visual asistido por modelos de lenguaje (Claude API) es probabilístico, puede contener errores ("alucinaciones"), y no constituye interpretación radiológica formal.
5. **Sin protección de datos del paciente garantizada.** El usuario es responsable de la deidentificación de datos antes de utilizar el software, y del cumplimiento de regulaciones de protección de datos aplicables (LFPDPPP en México, GDPR en Europa, HIPAA en EE.UU., etc.).

### Responsabilidad del usuario

El usuario es el único responsable de:

- Asegurar el cumplimiento legal y ético del uso del software en su jurisdicción
- Obtener el consentimiento informado apropiado antes de procesar datos de pacientes
- Anonimizar los datos antes de compartirlos con cualquier servicio externo (incluida la API de Claude)
- Validar cualquier resultado contra métodos clínicamente aceptados antes de tomar cualquier decisión
- Consultar a profesionales médicos calificados para la interpretación clínica de cualquier resultado

### Sin garantía

El software se proporciona "tal cual", sin ninguna garantía de ningún tipo. Los autores y contribuyentes no asumen ninguna responsabilidad por daños directos, indirectos, incidentales, especiales, o consecuentes derivados del uso o la imposibilidad de uso del software, incluso si han sido advertidos de la posibilidad de tales daños.

### Decisiones clínicas

**Cualquier decisión médica o terapéutica relativa a un paciente debe basarse en:**

1. Evaluación clínica directa por profesionales calificados
2. Estudios de imagen interpretados por radiólogos certificados
3. Herramientas con registro sanitario apropiado en la jurisdicción aplicable
4. Discusión multidisciplinaria cuando corresponda

Los resultados generados por este software pueden, como máximo, complementar discusiones con especialistas, generar hipótesis para investigación, o servir con fines educativos.

---

## 🇬🇧 English

### Nature of the software

`neuro-analyzer` is an open-source software tool intended exclusively for **research, education, and learning purposes**. It produces quantitative measurements and structural descriptions from brain MRI images, by orchestrating established neuroimaging tools and language-model-assisted analysis.

### Not a medical device

This software:

- **HAS NOT** been approved, cleared, or registered by the FDA (USA), EMA (EU), MHRA (UK), Health Canada, COFEPRIS (Mexico), TGA (Australia), or any other regulatory health authority.
- **DOES NOT** meet the requirements of Software as a Medical Device (SaMD) under IMDRF, FDA, or other regulatory frameworks.
- **MUST NOT** be used for diagnosis, prevention, monitoring, treatment, or alleviation of disease.
- **MUST NOT** be used as the sole or primary basis for medical or therapeutic decisions.

### Inherent limitations

Users must understand that:

1. **Absence of clinical validation.** The software has not been validated in clinical cohorts. Its results have not been systematically compared against reference methods.
2. **Processing errors.** Underlying tools (FastSurfer, FreeSurfer when applicable) can produce segmentation errors, particularly in brains with malformations, lesions, or atypical anatomy.
3. **Training data biases.** Segmentation models are predominantly trained on adult cohorts and may have lower accuracy in pediatric populations.
4. **Probabilistic visual analysis.** Language-model-assisted visual analysis (Claude API) is probabilistic, can contain errors ("hallucinations"), and does not constitute formal radiological interpretation.
5. **No guaranteed patient data protection.** The user is responsible for deidentifying data before using the software, and for compliance with applicable data protection regulations (HIPAA in USA, GDPR in Europe, LFPDPPP in Mexico, etc.).

### User responsibility

The user is solely responsible for:

- Ensuring legal and ethical compliance of software use in their jurisdiction
- Obtaining appropriate informed consent before processing patient data
- Anonymizing data before sharing with any external service (including Claude API)
- Validating any results against clinically accepted methods before any decision-making
- Consulting qualified medical professionals for clinical interpretation of any results

### No warranty

The software is provided "as is", without warranty of any kind. Authors and contributors assume no liability for direct, indirect, incidental, special, or consequential damages arising from use or inability to use the software, even if advised of the possibility of such damages.

### Clinical decisions

**Any medical or therapeutic decision concerning a patient must be based on:**

1. Direct clinical evaluation by qualified professionals
2. Imaging studies interpreted by board-certified radiologists
3. Tools with appropriate regulatory clearance in the applicable jurisdiction
4. Multidisciplinary discussion when applicable

Results produced by this software may, at most, complement discussions with specialists, generate hypotheses for research, or serve educational purposes.
