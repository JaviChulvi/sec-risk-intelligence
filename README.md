# SEC Risk Intelligence

Análisis automático de riesgos ocultos en informes financieros usando LLMs.

Este repositorio está centrado en la parte de LLMs y evaluación del proyecto de
tesis. El baseline principal consume fixtures de evaluación autocontenidos, y
también incluye una integración exploratoria para descargar el último `10-K` de
una compañía desde la SEC y extraer secciones mediante `edgar-crawler`.

## Objetivo de Investigación

Los informes financieros declaran riesgos explícitos, pero también pueden
contener señales implícitas relevantes para inversores, auditores, consultores y
equipos de riesgo. El objetivo de la tesis es construir un flujo asistido por
LLMs que compare filings a lo largo del tiempo y detecte señales de riesgo
oculto como:

- Cambios de tono o urgencia entre filings consecutivos.
- Riesgos que aparecen, desaparecen o se vuelven menos específicos.
- Contradicciones entre `Risk Factors` y `MD&A`.
- Riesgos operativos, regulatorios, de ciberseguridad, mercado o clientes que
  estén implícitos en la discusión de management pero no claramente declarados.
- Cambios en el lenguaje de mitigación, confianza, incertidumbre o
  responsabilidad.

Cada hallazgo del modelo debe ser auditable: compañía, año, sección del filing y
texto de evidencia deben estar disponibles para revisión manual.

## Alcance Actual

El primer baseline es deliberadamente estrecho:

- Compañía: Guidewire Software, Inc. (`GWRE`)
- Filings: los últimos cinco informes anuales incluidos en el fixture
- Sección: `Item 1A. Risk Factors`
- Tarea: pedir al LLM que liste los encabezados explícitos de factores de riesgo
  declarados por la compañía

Esto todavía no es la tarea de riesgos ocultos. Es una prueba de cordura: antes
de pedir al modelo inferencias más sutiles, comprobamos que puede recuperar de
forma fiable los riesgos que ya están listados en el filing.

## Fixture de Evaluación

`eval.json` es autocontenido. Cada caso incluye:

- `company`, `ticker`, `cik`, `year` y metadata del filing
- `risk_factor_used`: metadata de la sección y recuento de palabras
- `input.text`: el texto completo de `Item 1A. Risk Factors` usado en el prompt
- `expected_result_by_llm`: la lista ordenada esperada de encabezados de riesgo
  declarados

El runner de evaluación no necesita archivos SEC locales ni textos extraídos en
otros ficheros. El futuro scraping o extracción debería producir el mismo formato
de fixture autocontenido para que la parte LLM sea reproducible.

## Entorno

Crea un archivo local `.env` y no lo commits.

```bash
DEEPSEEK_API_KEY="..."
DEEPSEEK_MODEL="..."
SEC_USER_AGENT="Tu Nombre tu.email@example.com"
```

Puedes crear o gestionar las API keys de DeepSeek desde la plataforma de
DeepSeek:

```text
https://platform.deepseek.com/usage
```

El cliente de DeepSeek carga `.env` cuando el notebook crea el cliente. Mantén
las claves fuera de notebooks, logs y archivos commiteados.

La SEC pide un `User-Agent` descriptivo para acceder a EDGAR. Usa
`SEC_USER_AGENT` con nombre y email reales cuando ejecutes notebooks que
descargan filings en vivo.

## Instalación

```bash
python3 -m pip install -e .
```

Para usar el notebook con tablas y gráficos:

```bash
python3 -m pip install -e ".[notebook]"
```

Para usar la integración de descarga/extracción SEC con `edgar-crawler`:

```bash
python3 -m pip install -e ".[data-extraction]"
```

Para ejecutar notebooks que combinan extracción y LLM, instala ambos extras:

```bash
python3 -m pip install -e ".[notebook,data-extraction]"
```

Ejecuta la suite de tests:

```bash
python3 -m pytest -q
```

## Ejecutar el Baseline con DeepSeek

Usa el notebook:

```text
notebooks/deepseek_risk_factor_eval.ipynb
```

Los outputs se escriben en:

```text
eval_runs/<run_id>/
```

Cada ejecución incluye `summary.json` y un archivo JSON por cada caso evaluado.
Los umbrales por defecto son:

- Recall: `0.98`
- Precision: `0.95`
- Similitud mínima del título: `0.88`

El notebook ejecuta todos los casos de `eval.json` por defecto y añade
comprobaciones previas, tablas de métricas, gráficos y análisis de errores.

## Ejecutar un 10-K Vivo con edgar-crawler

El notebook de integración descarga el último `10-K` disponible para JPMorgan
Chase & Co. (`JPM`), guarda una copia cacheada en el layout esperado por
`edgar-crawler`, extrae `Item 1A. Risk Factors` con `ExtractItems` y después
ejecuta el mismo prompt del baseline:

```text
notebooks/jpmorgan_latest_10k_risk_factor_prompt.ipynb
```

La API de alto nivel está en:

```python
from src.data_extraction import (
    fetch_company_10k_risk_factors,
    fetch_latest_10k_risk_factors,
)

# Caso puntual: último 10-K de JPM.
risk_section = fetch_latest_10k_risk_factors("JPM")

# Más general: últimos dos 10-K de una compañía.
sections = fetch_company_10k_risk_factors("JPM", limit=2)

# Años concretos por periodo de reporte.
sections = fetch_company_10k_risk_factors("JPM", report_years={2024, 2025})
```

Internamente, el flujo es:

1. Resolver ticker/CIK mediante la SEC.
2. Listar filings por `form`, `limit` y/o años de reporte.
3. Descargar el documento principal del filing.
4. Guardarlo bajo `data/edgar_crawler_live/RAW_FILINGS/<form>/`.
5. Construir la fila de metadata que espera `edgar-crawler`.
6. Ejecutar `edgar-crawler` `ExtractItems`.
7. Pasar `item_1A` al prompt de evaluación existente.

Los datos descargados y outputs de ejecución quedan ignorados por Git:

```text
data/
eval_runs/
```

## Cómo se Puntúa la Evaluación

En este baseline, esperamos que el modelo recupere los encabezados explícitos de
factores de riesgo ya declarados por la compañía. La respuesta esperada está
guardada en cada caso bajo:

```text
expected_result_by_llm.risk_factors[].title
```

La salida del modelo se parsea desde:

```text
risk_factors[].title
```

El scorer normaliza los títulos antes de compararlos: minúsculas, comillas,
reemplazo de `&` por `and`, eliminación de puntuación y colapso de espacios
repetidos. Después compara cada título esperado contra el mejor título predicho
que aún no se haya usado. Un match se acepta cuando la similitud es al menos el
umbral de similitud de título, actualmente `0.88`.

Para cada caso:

- `expected_count`: número de encabezados esperados en `eval.json`.
- `predicted_count`: número de encabezados devueltos por el modelo.
- `matched_count`: encabezados esperados emparejados correctamente con
  encabezados del modelo.
- `recall = matched_count / expected_count`.
- `precision = matched_count / predicted_count`.
- `missing`: encabezados esperados que el modelo no recuperó.
- `unexpected`: encabezados del modelo que no emparejan con la lista esperada.

Un caso pasa únicamente cuando se cumplen ambas condiciones:

- `recall >= 0.98`
- `precision >= 0.95`

La ejecución completa pasa solo si pasan todos los casos seleccionados. Esto
evita recompensar al modelo por producir muchos riesgos plausibles: debe
recuperar los encabezados declarados por la compañía sin omitir elementos
esperados ni añadir demasiados encabezados no soportados.

## Contrato con la Pipeline de Datos

La pipeline separada de scraping y extracción SEC debería entregar a este repo
un fixture JSON con la misma forma que `eval.json`. La forma mínima útil de un
caso es:

```json
{
  "id": "gwre-2025-10k-item-1a-risk-factor-listing",
  "company": "Guidewire Software, Inc.",
  "ticker": "GWRE",
  "cik": "0001528396",
  "year": 2025,
  "filing": {
    "form": "10-K",
    "filing_date": "2025-09-15",
    "accession_number": "0001528396-25-000221"
  },
  "risk_factor_used": {
    "section": "Item 1A. Risk Factors",
    "source": "embedded_eval_json",
    "word_count": 20000
  },
  "input": {
    "section": "Item 1A. Risk Factors",
    "text": "Full section text..."
  },
  "expected_result_by_llm": {
    "risk_factor_count": 1,
    "risk_factors": [
      {
        "order": 1,
        "category": "Risks Related to our Business",
        "title": "Example disclosed risk heading."
      }
    ]
  }
}
```

Para las siguientes evaluaciones de riesgos ocultos, este fixture puede crecer e
incluir pares de años y múltiples secciones, especialmente `Risk Factors` junto
con `MD&A`.

## Flujo LLM Previsto

La pipeline prevista para riesgos ocultos es:

1. Recibir secciones extraídas desde la pipeline externa de datos.
2. Construir pares de años consecutivos, por ejemplo `2024 -> 2025`.
3. Pedir al LLM que compare las dos secciones y devuelva JSON estructurado.
4. Exigir spans de evidencia citados para cada hipótesis de riesgo oculto.
5. Guardar la salida del modelo junto al caso de evaluación.
6. Validar manualmente una muestra.

El prompt de comparación debería pedir al modelo que identifique:

- Riesgos nuevos introducidos este año.
- Riesgos eliminados o suavizados respecto al año anterior.
- Cambios de tono en severidad, urgencia, especificidad, incertidumbre o
  confianza.
- Contradicciones entre filings previos y actuales.
- Riesgos implícitos en `MD&A` que no estén claramente reflejados en
  `Risk Factors`.
- Cambios en lenguaje de mitigación o accountability.

El modelo debe poder devolver que no hay hallazgos cuando la evidencia sea
débil. El valor de la tesis viene de un análisis disciplinado y auditable, no de
forzar que cada par de años produzca un resultado dramático.

## Plan de Validación

Crea un pequeño conjunto etiquetado manualmente antes de escalar:

- Seleccionar varios pares de años de Guidewire.
- Muestrear hallazgos del modelo en distintos tipos de señal.
- Etiquetar manualmente si cada hallazgo está soportado por el texto citado.
- Medir falsos positivos, claims no soportados y cambios obvios omitidos.
- Revisar prompts y schemas de salida antes de añadir más compañías.

Métricas útiles de validación:

- Tasa de soporte por evidencia.
- Tasa de claims no soportados.
- Tasa de hallazgos duplicados.
- Puntuación de utilidad humana.
- Acuerdo entre etiquetas manuales y categorías del LLM.

## Estructura del Proyecto

```text
.
|-- README.md
|-- eval.json
|-- pyproject.toml
|-- requirements.txt
|-- notebooks/
|   |-- deepseek_risk_factor_eval.ipynb
|   `-- jpmorgan_latest_10k_risk_factor_prompt.ipynb
|-- src/
|   |-- data_extraction/
|   |   |-- company_filings.py
|   |   |-- sec_filings.py
|   |   |-- edgar_crawler_adapter.py
|   |   `-- edgar-crawler/
|   |-- evals/
|   |   `-- risk_factor_listing.py
|   |-- llm/
|   |   `-- deepseek.py
|   |-- prompts/
|   |   `-- risk_factor_listing.py
|   |-- settings.py
|   `-- tests/
|       |-- test_llm_eval.py
|       |-- test_sec_filings.py
|       `-- test_edgar_crawler_adapter.py
```

## Próximos Hitos

- Añadir el primer fixture de comparación year-over-year para riesgos ocultos.
- Definir el schema JSON estructurado para hallazgos de riesgo oculto.
- Escribir prompts que obliguen a citar evidencia y permitan no encontrar nada.
- Crear una plantilla de etiquetado manual para validación.
- Ejecutar el primer análisis de pares de años de Guidewire y revisar la salida
  manualmente.
