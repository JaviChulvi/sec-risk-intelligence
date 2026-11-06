# Contexto de traspaso: revisión de 57 candidatos EODHD

Fecha del estado: 2026-10-29.

## Próxima tarea

Preparar y revisar humanamente los 57 candidatos del conjunto de entrenamiento
`mag7-risk-train-2026-bf1`. El objetivo inmediato es medir la precisión real del
filtro y confirmar las familias de riesgo antes de volver a modificar reglas o
adquirir más noticias.

No se debe abrir todavía validación ni test. Esta revisión pertenece al conjunto
de entrenamiento y puede utilizarse posteriormente para ajustar el filtro.

## Artefactos que deben preservarse

Paquete original:

`data/processed/eodhd_mag7/datasets/mag7-risk-train-2026-bf1/`

Archivos principales:

- `risk_news_candidates.csv`;
- `risk_news_candidates.jsonl`;
- `dataset_manifest.json`;
- `manifest.json`;
- `articles_metadata.csv`.

Hashes observados antes de la revisión:

| Archivo | SHA-256 |
|---|---|
| `risk_news_candidates.csv` | `56be2bd84388e78684719d388a18aacde8a4deb55f4e1604ab27560646ec83da` |
| `risk_news_candidates.jsonl` | `25e74c48eab1bd2d40325b3d7d4541ed613fb759a781881f799338cd9f387648` |
| `dataset_manifest.json` | `58a69d95599985589e96459b3e666b7a6ff4c5be1e18f64c54df810747000e5a` |

### Regla de preservación

No anotar ni sobrescribir `risk_news_candidates.csv`: su hash está registrado en
el manifiesto y modificarlo rompería la procedencia del paquete. Tampoco se debe
regenerar el paquete con el mismo `dataset_id`.

El primer paso del siguiente chat debe ser crear una hoja derivada, por ejemplo:

`data/processed/eodhd_mag7/datasets/mag7-risk-train-2026-bf1/risk_news_candidates_review.csv`

La hoja derivada debe conservar los identificadores y metadatos originales y
añadir campos de anotación estructurados. No debe incluir cuerpos de noticias.

## Origen y alcance del conjunto

- Partición: `train`.
- Periodo solicitado: 2026-01-01 a 2026-09-30.
- Empresas: AAPL, MSFT, GOOGL y NVDA.
- Validación reservada: AMZN.
- Test reservado: META y TSLA.
- Estrategia de adquisición: paginación *breadth-first* por empresa y mes.
- Unidad presupuestaria: relación única `(empresa, article_id)`.
- Relaciones únicas admitidas: 9.861.
- Registros examinados antes del presupuesto: 11.690.
- Duplicados exactos descartados antes del presupuesto: 1.829.
- Llamadas HTTP nuevas: 100, sin reintentos.
- Motivo de parada: `max_http_attempts`.

Las 45 ventanas empresa-ticker-mes contienen artículos. El campo histórico
`windows_skipped_budget: 44` del manifiesto está mal nombrado: esas ventanas
quedaron parciales al terminar el presupuesto, pero no quedaron sin datos. El
código ya se corrigió para futuras ejecuciones; no se modificó retroactivamente
el paquete.

## Distribución de los 57 candidatos

### Por empresa

| Empresa | Candidatos |
|---|---:|
| AAPL | 25 |
| GOOGL | 15 |
| MSFT | 9 |
| NVDA | 8 |

### Por familia propuesta

| Familia | Candidatos |
|---|---:|
| `cybersecurity` | 36 |
| `critical_suppliers` | 16 |
| `customer_concentration` | 5 |

Las familias pueden solaparse si una noticia activa más de una regla. Hay 56
candidatos con contenido `full` y uno `summary_only`.

### Por mes de publicación

| Mes | Candidatos |
|---|---:|
| 2026-01 | 4 |
| 2026-02 | 1 |
| 2026-03 | 7 |
| 2026-04 | 7 |
| 2026-05 | 6 |
| 2026-06 | 9 |
| 2026-07 | 9 |
| 2026-08 | 7 |
| 2026-09 | 7 |

La cobertura temporal está equilibrada respecto a la primera adquisición, que
había quedado concentrada en enero. De los 57 candidatos actuales, 53 no estaban
en el paquete anterior y cuatro coinciden con él.

## Decisión provisional sobre `customer_concentration`

`customer_concentration` se ha excluido provisionalmente como clase objetivo del
dataset principal de noticias. Se mantiene como riesgo válido en el análisis de
`10-K` y sus cinco candidatos se conservan como material exploratorio.

La revisión debe incluir igualmente esas cinco filas y evaluarlas sin marcarlas
automáticamente como negativas. Su resultado servirá para comprobar y documentar
la decisión, pero no deben contarse de antemano como positivos entrenables.

Justificación completa:

`reports/eodhd_customer_concentration_exclusion.md`.

## Esquema recomendado para la hoja de revisión

Debe reutilizarse, en lo posible, el esquema ya empleado por
`risk_news_revised_new_candidates_review.csv`:

- `review_order`;
- `selection_provenance`;
- `article_id`;
- `company`;
- `published_at_utc`;
- `title`;
- `content_available`;
- `proposed_risk_families`;
- `risk_match_terms`;
- `link`;
- `review_status`;
- `relevant_risk_news`;
- `company_relevance`;
- `event_status`;
- `confirmed_risk_families`;
- `noise_type`;
- `reviewer`;
- `notes`.

Los campos de procedencia deben copiarse mecánicamente desde el paquete y no
editarse durante la anotación.

## Criterio de anotación

Para cada relación artículo-empresa se deben responder preguntas separadas:

1. ¿La noticia describe un riesgo, exposición o acontecimiento adverso real para
   la empresa consultada?
2. Si es positiva, ¿qué familia o familias están realmente respaldadas por el
   contenido?
3. ¿Se trata de un hecho `materialized`, una `exposure` estructural o un riesgo
   `emerging`?
4. Si es negativa, ¿qué tipo de ruido explica la activación?

Convenciones compatibles con el flujo anterior:

- `review_status`: `reviewed` al completar la fila;
- `relevant_risk_news`: `true` o `false` al cerrar la revisión;
- `company_relevance`: `true`, `false`, `unclear` o vacío si no se usa;
- `event_status` positivo: `materialized`, `exposure` o `emerging`;
- `confirmed_risk_families`: familias separadas por `|`;
- una fila positiva debe tener familia confirmada y no debe tener `noise_type`;
- una fila negativa debe tener `noise_type` y no debe tener familia confirmada ni
  `event_status`;
- `reviewer` y `notes` deben completarse para todas las filas.

Una coincidencia léxica no basta. Deben excluirse como negativas, entre otras:

- noticias sobre otra empresa sin exposición concreta para la consultada;
- análisis bursátil o recomendaciones de inversión sin riesgo empresarial real;
- predicciones genéricas;
- noticias rutinarias;
- menciones sectoriales sin vínculo material con la empresa;
- coincidencias terminológicas que no describen la familia propuesta.

Si el título no permite decidir, debe consultarse el cuerpo restringido mediante
`restricted_content_locators`. Los cuerpos permanecen bajo
`data/restricted/news/eodhd/normalized/` y no deben copiarse al CSV, al informe ni
a archivos versionables.

## Restricciones metodológicas

- Los 57 candidatos son datos de entrenamiento, no un holdout.
- Se pueden usar para desarrollar reglas, pero las métricas resultantes serán de
  desarrollo.
- No consultar ni adquirir AMZN, META o TSLA para ajustar el filtro.
- No cambiar la asignación empresarial de las particiones durante la revisión.
- No interpretar los 57 candidatos como 57 positivos.
- No estimar recall: solo se revisan noticias seleccionadas por el filtro.
- No hacer nuevas llamadas a EODHD para completar esta revisión; los cuerpos ya
  están en la caché restringida.
- Antes de abrir validación o test habrá que congelar el filtro definitivo y
  actualizar el protocolo, cuya razón de bloqueo todavía menciona el desarrollo
  de `customer_concentration` y ha quedado desactualizada tras su exclusión.

## Estado esperado al terminar la revisión

El siguiente chat debería dejar:

1. una hoja derivada con 57/57 filas anotadas y validada sin modificar el paquete;
2. recuentos de positivos y negativos por empresa, mes y familia propuesta;
3. precisión de selección y exactitud de familia sobre entrenamiento;
4. diagnóstico de falsos positivos por término y `noise_type`;
5. decisión sobre si `critical_suppliers` tiene suficiente precisión para seguir
   junto a `cybersecurity`;
6. reglas definitivas congeladas antes de abrir validación y test.

## Estado técnico

La última suite completa ejecutada antes de este traspaso terminó con:

```text
124 passed, 1 skipped
```

El árbol de trabajo contiene cambios y archivos nuevos del usuario y del piloto.
No deben revertirse ni eliminarse cambios ajenos.

