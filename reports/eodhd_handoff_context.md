# Contexto de traspaso: piloto EODHD MAG7

Fecha del estado: 2026-10-22.

Actualización 2026-10-29: se ha excluido provisionalmente
`customer_concentration` como clase objetivo del dataset principal de noticias,
sin retirarla del análisis de `10-K` ni borrar sus reglas o candidatos. La decisión,
su evidencia y las condiciones para reconsiderarla están en
`reports/eodhd_customer_concentration_exclusion.md`.

El punto de continuación vigente para el siguiente chat es la revisión de los 57
candidatos de entrenamiento y está autocontenido en
`reports/eodhd_57_candidate_review_handoff.md`. Las instrucciones antiguas que
aparecen más abajo se conservan como historial, pero ya no describen la próxima tarea.

## Petición con la que continuará el siguiente chat

La primera tarea será revisar el archivo ya anotado:

`data/processed/eodhd_mag7/risk_news_development_review.csv`

No debe regenerarse antes de leerlo y preservar las anotaciones del usuario.

## Objetivo y restricciones vigentes

El proyecto evalúa noticias posteriores a 10-K de las MAG7 en tres familias:

1. `customer_concentration`;
2. `critical_suppliers`;
3. `cybersecurity`.

Las noticias se usan como contraste exploratorio posterior, no para construir las
etiquetas de pérdida documental entre 10-K.

Restricciones expresas del usuario:

- no contratar servicios;
- no ejecutar el histórico completo sin una nueva autorización explícita;
- no hacer nuevas llamadas a EODHD sin autorización cuando no sean necesarias;
- conservar los cuerpos de noticias únicamente bajo `data/restricted/`;
- FNSPID está descartado como alternativa válida y no debe incorporarse al plan.

## Decisión sobre la fuente

La elección de EODHD puede considerarse cerrada como `GO_CON_COMPLEMENTOS`:

- EODHD es la fuente principal de adquisición para el piloto MAG7;
- no debe tratarse como fuente exhaustiva o exclusiva;
- hace falta una fuente complementaria para episodios locales o mal asociados al
  ticker, como la huelga de IF Metall;
- la baja precisión del filtro es un problema de selección y clasificación, no una
  razón para reabrir la comparación general de proveedores.

## Adquisición ya realizada

Se ejecutaron únicamente seis ventanas pequeñas de 11 días, ancladas tres días antes
y siete días después de la primera divulgación pública de cada episodio. La ejecución
consumió seis llamadas, sin errores ni reintentos, y recuperó 1.744 artículos. No se
ejecutó el histórico 2021-2026.

Resultados de contenido:

- 882 artículos `full`;
- 152 `partial`;
- 710 `summary_only`;
- 51 candidatos léxicos, 49 con contenido útil.

El corpus bruto y normalizado está bajo `data/restricted/news/eodhd/`. Los derivados
están bajo `data/processed/eodhd_mag7/known_episode_probe/`.

## Seis episodios de referencia

| Episodio | Familia esperada | Recuperado |
|---|---|---:|
| `AAPL-2021-NSO-LAWSUIT` | `cybersecurity` | sí |
| `AAPL-2022-ZHENGZHOU` | `critical_suppliers` | sí |
| `MSFT-2023-STORM-0558` | `cybersecurity` | sí |
| `MSFT-2024-MIDNIGHT-BLIZZARD` | `cybersecurity` | sí |
| `MSFT-2024-CROWDSTRIKE-OUTAGE` | `critical_suppliers` | sí |
| `TSLA-2023-IF-METALL` | `critical_suppliers` | no |

Métricas confirmadas:

- recuperación de episodios: 5/6 = 83,3 %;
- recuperación con familia correcta: 5/6 = 83,3 %;
- contenido útil entre episodios recuperados: 5/5 = 100 %.

Fuentes principales:

- `data/reference/news_mag7/eligible_known_episodes.json`;
- `data/processed/eodhd_mag7/known_episode_query_manifest.json`;
- `config/eodhd_known_episode_recovery_review.json`;
- `data/processed/eodhd_mag7/known_episode_probe/recovery_metrics.json`;
- `reports/eodhd_known_episode_recovery.md`.

## Diagnóstico del filtro léxico anterior

El filtro original aplica expresiones regulares sobre título y cuerpo y permite varias
familias por artículo. Es deliberadamente un filtro de alta exhaustividad, no una
decisión científica final.

En las 51 relaciones artículo-empresa revisadas dentro de las ventanas conocidas:

- 20 correspondían al episodio concreto;
- 31 no correspondían al episodio;
- precisión respecto al episodio: 20/51 = 39,2 %;
- exactitud de familia entre los 20 relevantes: 10/20 = 50 %;
- todos los 20 relevantes tenían contenido útil.

Estas cifras miden coincidencia con el episodio de la ventana. No permiten afirmar que
las otras 31 noticias sean ruido: una noticia puede no ser el episodio buscado y aun
así describir otro acontecimiento adverso válido para la misma empresa. Esta distinción
motivó el nuevo CSV de desarrollo.

Archivos relacionados:

- `data/processed/eodhd_mag7/known_episode_probe/known_episode_candidate_review.csv`;
- `data/processed/eodhd_mag7/known_episode_probe/candidate_review_metrics.json`;
- `reports/eodhd_known_episode_candidate_precision.md`.

## CSV de desarrollo que debe revisarse ahora

`data/processed/eodhd_mag7/risk_news_development_review.csv` contiene 69 relaciones:

- 20 positivos reutilizados porque una coincidencia confirmada con un episodio
  adverso implica que también es una noticia de riesgo válida;
- 18 negativos reutilizados de la muestra general reciente;
- 31 negativos de episodio que se devolvieron a `pending` para responder otra
  pregunta: si son una noticia adversa válida aunque no sean el episodio buscado.

El usuario ya terminó la nueva anotación. Estado observado antes de crear este
documento:

- 69/69 filas con `review_status=reviewed`;
- 20 con `relevant_risk_news=true`;
- 49 con `relevant_risk_news=false`;
- las 31 decisiones nuevas están marcadas `false`, con `noise_type=off_topic` y
  revisor `Higinio`;
- los 20 positivos conservan 6 activaciones de `cybersecurity` y 14 de
  `critical_suppliers`;
- los 18 negativos importados conservan sus tipos de ruido originales;
- `company_relevance` está vacío en las 69 filas, lo cual estaba documentado como
  opcional.

### Incidencia de formato que debe resolverse primero

El guardado manual alteró cuatro encabezados:

| Encabezado observado | Encabezado esperado |
|---|---|
| `**content_available` | `content_available` |
| `**&#x70;roposed_risk_families` | `proposed_risk_families` |
| `**event_status` | `event_status` |
| `**&#x63;onfirmed_risk_families` | `confirmed_risk_families` |

En las 31 filas recién editadas también aparecen prefijos `**` y entidades HTML en
algunos valores de `content_available` y `proposed_risk_families`. Los datos siguen
alineados por columna y las anotaciones humanas parecen conservarse, pero debe hacerse
una normalización mecánica y limitada antes de validar métricas. No se debe regenerar
el archivo, porque el generador rechaza correctamente sobrescribir anotaciones y una
regeneración destruiría el trabajo humano.

## Próximos pasos recomendados

1. Leer el CSV sin modificarlo y confirmar el alcance exacto de la corrupción de
   encabezados y valores.
2. Crear una copia de seguridad recuperable dentro de `data/processed/` antes de la
   reparación, o aplicar un parche mínimo que preserve todas las decisiones.
3. Normalizar solamente los cuatro encabezados y los prefijos/entidades introducidos
   en las columnas afectadas.
4. Validar las 69 filas: estados permitidos, positivos con familia confirmada,
   negativos con `noise_type`, revisor y notas, familias dentro de la taxonomía y
   correspondencia con los metadatos de adquisición.
5. Crear métricas específicas de desarrollo para selección y clasificación. No usar
   las antiguas métricas de coincidencia de episodio como precisión general.
6. Analizar falsos positivos por término, familia, empresa y tipo de ruido.
7. Mejorar `src/news/risk_filter.py` mediante reglas transparentes y configurables,
   separando selección de noticia adversa y clasificación de familia.
8. Reprocesar únicamente los datos locales en caché y comparar antes/después. No es
   necesaria ninguna llamada a EODHD.
9. Mantener al menos una evidencia por cada uno de los cinco episodios recuperados y
   vigilar especialmente la reclasificación de CrowdStrike como dependencia de
   proveedor crítico, no como ciberataque contra Microsoft.

## Advertencia metodológica sobre evaluación

El CSV es un conjunto de desarrollo. Sus 20 positivos proceden de episodios que ya se
han inspeccionado y sus etiquetas no son un holdout ciego. Si se usa para ajustar
reglas o umbrales, las métricas posteriores serán métricas de desarrollo, no una
estimación final independiente. Antes de afirmar rendimiento generalizable hará falta
un conjunto nuevo, anotado y congelado, idealmente con representación de las tres
familias. Actualmente no existe ningún episodio de referencia elegible de
`customer_concentration`.

La decisión de adquisición `GO_CON_COMPLEMENTOS` sí puede mantenerse: se fundamenta
en recuperación y calidad del contenido, y no depende de presentar el filtro actual
como un clasificador final.

## Implementación añadida en el último paso

- `src/news/risk_news_development_review.py`: genera la hoja consolidada, reutiliza
  solo inferencias seguras y protege anotaciones existentes;
- `src/news/__main__.py`: incorpora el comando `risk-development-review`;
- `src/tests/test_news_risk_development_review.py`: prueba separación de etiquetas y
  protección contra sobrescritura;
- `src/news/README.md`: documenta el flujo y su limitación como conjunto de desarrollo.

El comando generador es:

```bash
.venv/bin/python -m src.news eodhd risk-development-review \
  --config config/eodhd_pilot.json
```

No debe ejecutarse ahora sobre el CSV anotado.

Último resultado de pruebas antes de este documento:

```text
99 passed, 1 skipped
```

El árbol de trabajo contiene cambios no confirmados y archivos nuevos del piloto. No
deben revertirse ni eliminarse cambios ajenos.

## Preferencias de implementación que siguen vigentes

- buscar y extender código existente antes de duplicarlo;
- usar POO cuando mejore la encapsulación, sin forzarla en transformaciones simples;
- señalar errores o riesgos antes de ejecutar;
- usar `apply_patch` para editar archivos;
- no exponer `EODHD_API_TOKEN`;
- no guardar rutas personales absolutas en archivos versionables;
- para CSV se está usando el escritor interno del repositorio porque el runtime
  especializado de hojas de cálculo no estaba disponible; el usuario autorizó este
  fallback.
