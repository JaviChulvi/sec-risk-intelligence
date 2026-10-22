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

## Interpretación

`content_available` se asigna mediante reglas transparentes de longitud,
truncamiento, igualdad con el titular y páginas de error/consentimiento. No usa un
LLM. El filtro de riesgo es de alta exhaustividad y conserva los términos que lo
activaron. La deduplicación conserva todos los registros. Los `event_id` son solo
propuestas con `review_status: candidate`.

El informe solo puede recomendar `GO`, `GO_CON_COMPLEMENTOS` o `NO_GO` cuando existe
una ejecución de piloto y una tasa revisada de recuperación por episodio. Un smoke
test produce `PENDIENTE`, porque funcionamiento técnico y conclusión científica no
son equivalentes.

La revisión se mide por relación artículo-empresa, porque un mismo artículo puede
ser pertinente para una empresa y ruido para otra. El comando `review` valida las
anotaciones, registra el SHA-256 del CSV y separa la tasa observada en la muestra de
un límite superior conservador para los candidatos que aún no se han revisado. Una
revisión asistida por IA se identifica como diagnóstico, no como gold standard humano.

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
