# OCR Manuscrito -> REDCap

Pipeline por lotes para:
- leer PDFs de pacientes (`input/pdfs/*.pdf`) con texto manuscrito,
- extraer datos a JSON (`output/json/*.json`),
- rellenar parcialmente REDCap con un flujo fijo por teclado.

Modo actual del scraper:
- espera CAPTCHA manual + `Enter` en terminal,
- ejecuta una secuencia rígida de `TAB` + flechas + texto,
- usa valores desde el JSON,
- no se cierra automáticamente al acabar.

## 1) Requisitos

- Python `3.12+`
- Entorno virtual `.venv` (ya creado)
- Dependencias Python en `requirements.txt` (versiones exactas)
- Binarios de sistema:
  - `tesseract` (OCR)
  - `poppler` (conversión PDF->imagen para `pdf2image`)
- Navegador Playwright:
  - `./.venv/bin/playwright install chromium`

Ejemplo instalación en macOS (Homebrew):

```bash
brew install tesseract poppler
```

## 2) Estructura

- `input/pdfs`: PDFs fuente (`paciente1.pdf`, `paciente2.pdf`, ...)
- `config/form_schema.json`: plantilla de campos + mapeo formulario
- `src/extract_from_pdf.py`: OCR y extracción a JSON
- `src/fill_redcap.py`: autocompletado REDCap desde JSON
- `src/run_batch.py`: ejecución completa por lotes
- `output/json`: JSON extraído por paciente
- `output/screenshots`: capturas en errores de envío
- `output/ingestion_log.json`: log consolidado de ingestión

## 3) Activar entorno

```bash
source .venv/bin/activate
```

## 4) Configurar mapeo del formulario

Edita `config/form_schema.json`:

- `survey_url`: URL del formulario REDCap.
- `fixed_form`: bloque fijo (constante para todos los pacientes).
- `demografia.fields`: campos que se extraen del PDF por OCR.
- `navigation.continue_button_texts`: textos válidos para el botón de continuar.

Formato de salida JSON por paciente:

```json
{
  "source_pdf": "paciente1.pdf",
  "fixed_form": {
    "email": "adrian@something.com",
    "hospital": "España",
    "hospital_espanol": "Asturias - Hospital Valle del Nalón",
    "criterios_inclusion": {
      "dosis_estable_clozapina_4_semanas": "Sí",
      "edad_mayor_18": "Sí",
      "discapacidad_cognitiva": "No",
      "prescripcion_mas_dos_antipsicoticos": "No",
      "patologia_medica_no_controlada": "No"
    }
  },
  "demografia": {
    "fecha_consentimiento_informado": "11-04-2026",
    "edad": 80,
    "genero": "Hombre",
    "nivel_educativo": "Iletrado",
    "ocupacion": "Desempleado",
    "diagnostico": "Esquizofrenia",
    "otras_patologias_fisicas": "texto libre"
  }
}
```

Notas:
- bloque `fixed_form`: siempre igual (no OCR).
- bloque `demografia`: extraído desde OCR manuscrito.
- cuando OCR no resuelve bien, `requires_review` queda en `true`.

## 5) Ejecutar batch completo

```bash
python src/run_batch.py
```

Opciones:
- `--headless`: ejecuta navegador oculto.
- `--no-skip-completed`: reprocesa pacientes ya completados.
- `--input-dir`, `--json-dir`, `--log-path`, `--schema`, `--screenshot-dir`: rutas custom.

Nota:
- el scraper actual es manual y parcial; no se recomienda usar `run_batch.py` como proceso desatendido.

## 6) Flujo CAPTCHA (manual asistido)

Cuando `fill_redcap.py` detecta CAPTCHA:
- abre REDCap,
- esperas a resolver CAPTCHA manualmente,
- pulsas Enter en terminal y entonces empieza el flujo fijo de teclado.

## 7) Salidas y control de ingestión

### JSON por paciente (`output/json/pacienteN.json`)

Incluye:
- `fixed_form`: valores constantes de la primera pantalla,
- `demografia`: valores variables extraídos por OCR,
- `extraction_confidence`: score global,
- `field_confidence`: score por campo,
- `missing_required`, `low_confidence_fields`,
- `requires_review` para revisión manual.

### Log consolidado (`output/ingestion_log.json`)

Cada entrada guarda:
- paciente y PDF origen,
- `status`: `completed` / `failed` / `skipped`,
- `moved_to_next_page` (si logró pulsar continuar),
- error y screenshot si aplica.

## 8) Ejecución por pasos (debug)

Extraer solo 1 PDF:

```bash
python src/extract_from_pdf.py --pdf input/pdfs/paciente1.pdf
```

Rellenar REDCap desde 1 JSON:

```bash
python src/fill_redcap.py --json output/json/paciente1.json
```

Opciones útiles:
- `--auto-close`: cierra navegador al terminar.
- sin `--auto-close`: deja navegador abierto hasta `Ctrl+C`.

Flujo actual implementado:
- usa `fixed_form.email`
- usa `demografia.fecha_consentimiento_informado`
- usa `demografia.edad`
- por ahora termina después de escribir `edad`

## 9) Limitaciones esperables

- OCR manuscrito no es perfecto; usa `requires_review` como filtro.
- el flujo depende completamente del orden de tabulación actual del formulario.
- si REDCap cambia el orden de foco/HTML, habrá que retocar la secuencia de `TAB` y flechas en `src/fill_redcap.py`.
