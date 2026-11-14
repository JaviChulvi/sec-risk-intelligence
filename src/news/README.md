# Piloto EODHD para noticias MAG7

Este módulo evalúa EODHD como fuente complementaria de evidencia posterior a los
10-K. No etiqueta pérdidas documentales, no considera que una noticia equivalga a
un acontecimiento y no interpreta una consulta vacía como ausencia cierta de hechos.

## Seguridad y almacenamiento

El modo `demo` usa literalmente el token público `demo`. El modo `pilot` lee
`EODHD_API_TOKEN` del entorno; la clave no se acepta como argumento, no se serializa
y no aparece en los errores generados por el cliente.

Las respuestas originales y los normalizados con cuerpo se guardan bajo
`data/restricted/news/eodhd/`. Los derivados sin cuerpo se escriben en
`data/processed/eodhd_mag7/`. Ambas rutas están ignoradas por Git. No se visitan
las URL de los artículos ni se intenta eludir paywalls u otras restricciones.

## Ejecución

```bash
# Mostrar las ventanas sin llamar a la API
python3 -m src.news eodhd run --config config/eodhd_pilot.json \
  --mode demo --from 2026-10-13 --to 2026-10-19 --dry-run

# Smoke test gratuito y acotado
python3 -m src.news eodhd run --config config/eodhd_pilot.json \
  --mode demo --from 2026-10-13 --to 2026-10-19

# Piloto con clave propia; las fechas son obligatorias
EODHD_API_TOKEN=... python3 -m src.news eodhd run \
  --config config/eodhd_pilot.json --mode pilot \
  --from 2025-01-01 --to 2025-01-31

# Previsualizar un dataset acotado de las siete compañías, sin llamar a EODHD
python3 -m src.news eodhd dataset \
  --dataset-id mag7-risk-2025q1 \
  --from 2025-01-01 --to 2025-03-31 \
  --max-acquired-articles 5000 --max-network-pages 50 --max-http-attempts 60 \
  --max-candidates 500 --dry-run

# Ejecutar y empaquetar (requiere clave y autorización para consumir la API)
EODHD_API_TOKEN=... python3 -m src.news eodhd dataset \
  --dataset-id mag7-risk-2025q1 \
  --from 2025-01-01 --to 2025-03-31 \
  --max-acquired-articles 5000 --max-network-pages 50 --max-http-attempts 60 \
  --max-candidates 500

# Previsualizar solo entrenamiento bajo la partición empresarial congelada
python3 -m src.news eodhd dataset \
  --dataset-id mag7-risk-train-2026 \
  --from 2026-01-01 --to 2026-09-30 \
  --split-config config/eodhd_dataset_split.json --split-stage train \
  --max-acquired-articles 10000 --max-http-attempts 100 \
  --max-candidates 800 --dry-run

# Primera adquisición de entrenamiento 2021-2026 para las dos familias objetivo
# El protocolo fija las familias; no es necesario repetir --risk-families.
python3 -m src.news eodhd dataset \
  --dataset-id mag7-risk-train-2021-2026-bf1 \
  --from 2021-01-01 --to 2026-09-30 \
  --split-config config/eodhd_dataset_2021_2026.json --split-stage train \
  --max-acquired-articles 120000 --max-network-pages 1080 \
  --max-http-attempts 1200 --max-candidates 800 --dry-run

# Crear una hoja derivada de revisión humana sin modificar los candidatos
python3 -m src.news eodhd dataset-review-sheet \
  --candidates data/processed/eodhd_mag7/datasets/mag7-risk-train-2021-2026-bf1/risk_news_candidates.csv \
  --output data/processed/eodhd_mag7/datasets/mag7-risk-train-2021-2026-bf1/risk_news_candidates_review.csv

# Crear una muestra común y copias independientes para calibrar anotadores
python3 -m src.news eodhd dataset-calibration-sample \
  --review data/processed/eodhd_mag7/datasets/mag7-risk-train-2021-2026-bf1/risk_news_candidates_review.csv \
  --candidates data/processed/eodhd_mag7/datasets/mag7-risk-train-2021-2026-bf1/risk_news_candidates.csv \
  --output-dir data/processed/eodhd_mag7/datasets/mag7-risk-train-2021-2026-bf1/calibration \
  --annotators Javi Hugo Higinio --sample-size 40 \
  --seed mag7-risk-calibration-2021-2026-v1

# Validar las tres anotaciones completas y guardar acuerdos y discrepancias
python3 -m src.news eodhd dataset-calibration-compare \
  --manifest data/processed/eodhd_mag7/datasets/mag7-risk-train-2021-2026-bf1/calibration/calibration_sample_40_manifest.json \
  --reviews \
    data/processed/eodhd_mag7/datasets/mag7-risk-train-2021-2026-bf1/calibration/calibration_sample_40_javi.csv \
    data/processed/eodhd_mag7/datasets/mag7-risk-train-2021-2026-bf1/calibration/calibration_sample_40_hugo.csv \
    data/processed/eodhd_mag7/datasets/mag7-risk-train-2021-2026-bf1/calibration/calibration_sample_40_higinio.csv \
  --output data/processed/eodhd_mag7/datasets/mag7-risk-train-2021-2026-bf1/calibration/calibration_comparison.json

# Crear la hoja protegida para resolver únicamente las discrepancias
python3 -m src.news eodhd dataset-calibration-consensus-sheet \
  --comparison data/processed/eodhd_mag7/datasets/mag7-risk-train-2021-2026-bf1/calibration/calibration_comparison.json \
  --output data/processed/eodhd_mag7/datasets/mag7-risk-train-2021-2026-bf1/calibration/calibration_consensus.csv

# Generar el informe sin repetir descargas
python3 -m src.news eodhd report --config config/eodhd_pilot.json

# Validar la muestra anotada y calcular métricas; no llama a la API ni altera el CSV
python3 -m src.news eodhd review --config config/eodhd_pilot.json

# Regenerar el informe para incorporar review_metrics.json
python3 -m src.news eodhd report --config config/eodhd_pilot.json

# Filtrar localmente las 49 fichas en episodios conocidos elegibles
python3 -m src.news eodhd reference-filter --config config/eodhd_pilot.json

# Generar el manifiesto de ventanas -3/+7 y mostrar el dry-run sin API ni credencial
python3 -m src.news eodhd episode-dry-run --config config/eodhd_pilot.json

# Ejecutar exactamente las ventanas validadas del manifiesto (requiere autorización)
python3 -m src.news eodhd episode-run --config config/eodhd_pilot.json

# Calcular métricas después de confirmar humanamente las coincidencias
python3 -m src.news eodhd episode-metrics --config config/eodhd_pilot.json

# Preparar los 51 candidatos léxicos para revisar precisión y tipos de ruido
python3 -m src.news eodhd episode-candidate-review --config config/eodhd_pilot.json

# Validar la revisión completa y calcular precisión por artículo, episodio y familia
python3 -m src.news eodhd episode-candidate-metrics --config config/eodhd_pilot.json

# Crear la hoja de desarrollo separada para selección y clasificación
python3 -m src.news eodhd risk-development-review --config config/eodhd_pilot.json
python3 -m src.news eodhd risk-development-metrics --config config/eodhd_pilot.json
python3 -m src.news eodhd risk-revised-candidate-review --config config/eodhd_pilot.json
```

El cliente divide el intervalo en meses, pagina de forma acotada, reintenta `429`
y errores transitorios `5xx` con espera exponencial y jitter, y subdivide una
ventana antes de alcanzar el techo configurado de `offset`. Una ventana errónea
queda registrada de forma saneada sin cancelar las demás; un error de autenticación
detiene la ejecución.

Cada página conserva JSON original, SHA-256, fecha UTC y parámetros sin credencial.
El estado permite reutilizar páginas verificadas y ventanas completas. Cambiar la
configuración de adquisición exige otra ruta para no mezclar consultas incompatibles;
cambiar reglas de procesamiento reutiliza el JSON bruto y regenera los derivados sin
consumir nuevas llamadas.

El comando `dataset` separa tres topes. `--max-acquired-articles`
limita de forma dura las relaciones únicas `(empresa, article_id)` admitidas,
incluidas las leídas de caché. Los duplicados exactos se descartan antes de cargar
ese presupuesto. `--max-http-attempts` limita las llamadas HTTP, incluidos los
reintentos, y `--max-candidates` limita el paquete filtrado final. El parámetro
opcional `--max-network-pages` añade un techo de páginas lógicas nuevas.

La adquisición de `dataset` recorre las páginas en rondas *breadth-first*: asigna
una porción equitativa del presupuesto restante a cada ventana empresa-mes antes de
profundizar en su siguiente página. El mismo reparto se aplica a páginas grandes ya
presentes en caché. El manifiesto distingue registros considerados, duplicados
descartados y relaciones únicas cargadas al presupuesto. Después, los candidatos se
seleccionan de forma determinista por estratos empresa-familia para reducir el sesgo
del corte, sin convertir la muestra en una muestra probabilística.

Cada `--dataset-id` escribe en su propia ruta bajo
`data/processed/eodhd_mag7/datasets/` y no sobrescribe un paquete existente. El
paquete contiene `risk_news_candidates.csv`, `risk_news_candidates.jsonl` y
`dataset_manifest.json`; no incluye cuerpos. Las filas llevan localizadores hacia
la caché normalizada restringida, estado inicial `candidate`, hashes de procedencia,
presupuesto consumido y limitaciones metodológicas. El filtro propone candidatos:
no sustituye una validación humana ni permite interpretar noticias no recuperadas
como ausencia de riesgo.

`dataset-review-sheet` transforma un CSV de candidatos empaquetado en una hoja de
anotación separada, sin cuerpos y con estado inicial `pending`. Comprueba que los
rangos y las relaciones sean únicos, conserva la procedencia del `dataset_id` y se
niega a sobrescribir el archivo en cuanto detecta una anotación humana.

La partición congelada de `config/eodhd_dataset_split.json` asigna Apple, Microsoft,
Alphabet y NVIDIA a entrenamiento; Amazon a validación; y Meta y Tesla a test. Usa
el periodo no inspeccionado del 1 de enero al 30 de septiembre de 2026 y rechaza por
configuración cualquier fecha distinta o solapada con los intervalos previamente
inspeccionados. Al indicar `--split-config`, la etapa predeterminada es `train`; las
etapas `validation`, `test` y `all` permanecen bloqueadas hasta registrar el hash del
filtro definitivo en el protocolo. El paquete
marca cada relación con su partición y elimina de las particiones de menor prioridad
cualquier noticia cuyo `article_id` o URL canónica ya aparezca en otra partición.

El protocolo ampliado `config/eodhd_dataset_2021_2026.json` conserva las mismas
empresas, pero admite periodos distintos por partición. Entrenamiento cubre del 1 de
enero de 2021 al 30 de septiembre de 2026; validación y test permanecen limitados al
periodo no inspeccionado de enero-septiembre de 2026. Esta asimetría evita presentar
AMZN, META o TSLA de 2021-2025 como datos ciegos después de haberlos utilizado en el
inventario de referencia. El protocolo fija `cybersecurity` y
`critical_suppliers` como únicas familias objetivo y obliga a adquirir cada etapa
por separado. Su primera fase permite hasta 1.080 páginas lógicas y 1.200 intentos
HTTP para 345 ventanas ticker-mes de entrenamiento; las ventanas con menos de una
página completa terminan antes automáticamente.

Esos topes son de una invocación. Si una adquisición se reanuda en varias
invocaciones, el consumo total debe controlarse mediante los contadores históricos
del manifiesto o mediante un límite externo; no debe inferirse sumando solo el
`acquisition_budget` de la última ejecución.

## Interpretación

`content_available` se asigna mediante reglas transparentes de longitud,
truncamiento, igualdad con el titular y páginas de error/consentimiento. No usa un
LLM. El filtro de riesgo es de alta exhaustividad y conserva los términos que lo
activaron. El piloto normal conserva los duplicados y los agrupa; `dataset` elimina
duplicados exactos de la misma relación artículo-empresa antes de aplicar su
presupuesto. Los `event_id` son solo propuestas con `review_status: candidate`.

El informe solo puede recomendar `GO`, `GO_CON_COMPLEMENTOS` o `NO_GO` cuando existe
una ejecución de piloto y una tasa revisada de recuperación por episodio. Un smoke
test produce `PENDIENTE`, porque funcionamiento técnico y conclusión científica no
son equivalentes.

La revisión se mide por relación artículo-empresa, porque un mismo artículo puede
ser pertinente para una empresa y ruido para otra. El comando `review` valida las
anotaciones, registra el SHA-256 del CSV y separa la tasa observada en la muestra de
un límite superior conservador para los candidatos que aún no se han revisado. Una
revisión asistida por IA se identifica como diagnóstico, no como gold standard humano.

La exclusión de `customer_concentration` como clase objetivo del dataset
principal de noticias, junto con su evidencia, alcance y condiciones de reapertura,
está documentada en
[`reports/eodhd_customer_concentration_exclusion.md`](../../reports/eodhd_customer_concentration_exclusion.md).
La familia se mantiene en el análisis de `10-K` y como material exploratorio.
El papel del filtro como recuperador de candidatos —y no como etiquetador
automático— y la necesidad de revisión humana posterior se documentan para la
memoria del TFM en
[`reports/eodhd_candidate_filter_human_review.md`](../../reports/eodhd_candidate_filter_human_review.md).

El filtro de referencia usa la publicación del segundo 10-K como `t0`, exige que
acontecimiento, primera divulgación y noticia estén dentro de los doce meses
posteriores, limita las familias a las tres del piloto y agrupa seguimientos del
mismo episodio. Las decisiones quedan como `candidate` y reservadas de cualquier
ajuste del filtro léxico.

El dry-run de episodios toma `first_public_disclosure_at` como ancla y crea una
ventana de tres días antes a siete después. Escribe parámetros iniciales sin
`api_token`; no lee el entorno ni instancia el cliente EODHD. El recuento de llamadas
es un mínimo que no incluye posibles páginas, reintentos o subdivisiones de una
ejecución real.

La revisión de candidatos conserva las 51 relaciones artículo-empresa activadas por
el filtro. Para cada fila se cambia `review_status` a `reviewed` y se completa
`relevant_to_window_episode` con `true`, `false` o `unclear`. Una fila relevante debe
indicar `confirmed_episode_id`, `confirmed_risk_family` y si la familia propuesta era
correcta; una fila no relevante debe indicar `noise_type`. `prior_evidence_role` es
solo contexto de la revisión confirmada anterior y no sustituye la nueva anotación.

La hoja `risk_news_development_review.csv` no equipara una noticia ajena al episodio
de una ventana con ruido del filtro. Reutiliza únicamente dos inferencias seguras:
una coincidencia positiva con un episodio adverso es también una noticia de riesgo
válida, y un negativo de la muestra general sigue siendo negativo. Los negativos de
episodio vuelven a `pending` y deben responder a otra pregunta: si describen un hecho
adverso materializado, vinculado a la empresa consultada y perteneciente a una de las
tres familias. Para esas filas se completa `relevant_risk_news` (`true`, `false` o
`unclear`); si es `true`, también `confirmed_risk_families`; si es `false`,
`noise_type`. `company_relevance` y `event_status` son campos diagnósticos opcionales.

Esta hoja es de desarrollo. Una vez usada para ajustar reglas o umbrales, no puede
servir como evaluación final independiente; hará falta un conjunto nuevo y congelado.

El comando `risk-development-metrics` valida las anotaciones contra los metadatos de
adquisición, compara el filtro almacenado con las reglas actuales sobre las cachés
locales y genera métricas de selección y clasificación separadas. No realiza llamadas
a EODHD ni modifica los cuerpos restringidos. Sus resultados son métricas de
desarrollo, no una estimación sobre un holdout independiente. Los candidatos nuevos
del filtro revisado se contabilizan como no etiquetados y no entran en su precisión.
`risk-revised-candidate-review` exporta únicamente esos candidatos nuevos a una hoja
sin cuerpos de noticias y rechaza sobrescribirla en cuanto contiene anotaciones.
Cuando esa hoja está revisada, `risk-development-metrics` valida sus campos contra
las cachés y compara ambos filtros sobre la unión completa de candidatos.

## Pruebas

```bash
python3 -m pytest -q src/tests/test_eodhd_provider.py \
  src/tests/test_news_normalization.py \
  src/tests/test_news_deduplication.py \
  src/tests/test_news_risk_filter.py \
  src/tests/test_news_event_cluster.py
```

Las pruebas ordinarias usan respuestas sintéticas. La integración real está
marcada como `integration` y se omite si no existe `EODHD_API_TOKEN`.
