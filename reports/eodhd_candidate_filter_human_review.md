# Papel del filtro de noticias y necesidad de revisión humana

Fecha de consolidación metodológica: 2026-11-01.

## Decisión metodológica

El filtro de noticias EODHD se utiliza como un mecanismo de **recuperación de
candidatos** para las familias `cybersecurity` y `critical_suppliers`. No se
considera un clasificador final y sus activaciones no constituyen etiquetas de
verdad de terreno. Toda relación artículo-empresa seleccionada debe someterse a
revisión humana antes de incorporarse al dataset anotado.

`customer_concentration` se excluye como familia objetivo del dataset principal de
noticias. La exclusión no afecta al análisis de los `10-K`, donde continúa siendo
una exposición empresarial válida. Su tratamiento detallado se documenta en
`reports/eodhd_customer_concentration_exclusion.md`.

## Evidencia empírica

La adquisición de entrenamiento `mag7-risk-train-2026-bf1` examinó 9.861
relaciones únicas artículo-empresa y generó 57 candidatos léxicos. La revisión
estructurada posterior produjo:

| Resultado de revisión | Relaciones |
|---|---:|
| Noticias relevantes para alguna familia objetivo | 21 |
| Negativos o ruido para las familias objetivo | 36 |
| Total revisado | 57 |

La distribución por familia propuesta fue:

| Familia propuesta | Candidatos | Familia confirmada | Precisión de familia observada |
|---|---:|---:|---:|
| `cybersecurity` | 36 | 11 | 30,6 % |
| `critical_suppliers` | 16 | 8 | 50,0 % |
| `customer_concentration` | 5 | 1 | 20,0 % |

Una relación activada por `customer_concentration` se reclasificó como
`critical_suppliers`. Por este motivo hay 21 noticias relevantes, pero solo 20
tienen al menos una familia propuesta originalmente que haya sido confirmada; la
restante fue recuperada con una familia incorrecta. Además, una noticia confirma
simultáneamente `cybersecurity` y `critical_suppliers`.

Estas cifras son métricas de desarrollo. La muestra contiene únicamente artículos
recuperados por el filtro y, por tanto, permite estudiar precisión de selección y
errores de clasificación, pero no estimar *recall*. Una noticia no recuperada no
puede interpretarse como evidencia de que el riesgo o el acontecimiento no exista.

Fuente principal:
`data/processed/eodhd_mag7/datasets/mag7-risk-train-2026-bf1/risk_news_candidates_review.csv`.

## Razones por las que la revisión humana sigue siendo necesaria

El filtro utiliza reglas transparentes y términos de alta cobertura. Esa estrategia
es apropiada para reducir el universo de noticias, pero produce ambigüedades que no
pueden resolverse únicamente mediante coincidencias léxicas. La revisión observó,
entre otros, los siguientes tipos de ruido:

- noticias sobre otra empresa en las que la compañía consultada aparece solo como
  cliente, proveedor, competidor o fuente investigadora;
- inversión de la relación comercial, por ejemplo atribuir al comprador la
  concentración de clientes que afecta al proveedor;
- usos no informáticos de términos como `breach`;
- riesgo regulatorio, de privacidad o de competencia confundido con
  `cybersecurity`;
- productos y servicios de seguridad que responden a una amenaza, pero no prueban
  que la empresa haya sufrido un incidente;
- escasez sectorial sin vínculo material con el aprovisionamiento de la empresa;
- tarjetas de recomendación, enlaces y módulos editoriales ajenos al cuerpo
  principal;
- análisis bursátil o predicciones que mencionan un término de riesgo sin aportar
  una exposición empresarial suficiente;
- múltiples publicaciones sindicadas del mismo acontecimiento.

También se observaron reclasificaciones legítimas. Una noticia puede ser relevante
aunque la familia que activó su selección sea incorrecta, y puede confirmar más de
una familia. Por ello la anotación separa explícitamente:

1. relevancia de la relación artículo-empresa;
2. familia o familias realmente confirmadas;
3. estado del riesgo: `materialized`, `exposure` o `emerging`;
4. tipo de ruido cuando la relación es negativa.

Los duplicados o noticias sindicadas no deben convertirse artificialmente en
negativos. Deben conservar la misma decisión semántica y controlarse mediante
`duplicate_group_id`, URL canónica o agrupación por evento.

## Diseño del dataset 2021-2026

El protocolo `config/eodhd_dataset_2021_2026.json` fija las siguientes decisiones:

- familias objetivo: `cybersecurity` y `critical_suppliers`;
- unidad de análisis: relación única `(empresa, article_id)`;
- entrenamiento: AAPL, MSFT, GOOGL y NVDA;
- validación: AMZN;
- test: META y TSLA;
- periodo de entrenamiento: 2021-01-01 a 2026-09-30;
- periodo de validación y test: 2026-01-01 a 2026-09-30;
- adquisición mensual con paginación *breadth-first*;
- cuerpos almacenados únicamente en la caché restringida;
- candidatos y metadatos derivados sin cuerpos.

Los periodos son deliberadamente asimétricos. Las noticias de AMZN, META y TSLA de
2021-2025 ya intervinieron en el inventario de referencia y no pueden presentarse
como un holdout ciego. El historial 2021-2026 se utiliza solo para las empresas de
entrenamiento. Validación y test permanecen bloqueados hasta congelar el filtro.

La primera fase de adquisición de entrenamiento contiene 345 ventanas ticker-mes:
AAPL, MSFT y NVDA aportan un ticker cada una, y Alphabet aporta GOOG y GOOGL. El
presupuesto inicial es de 1.080 páginas lógicas, 1.200 intentos HTTP y 120.000
relaciones únicas. Son límites máximos, no objetivos de consumo. Las ventanas con
menos resultados finalizan antes y solo se profundiza en aquellas que mantienen
otra página disponible.

## Resultado de la primera adquisición de entrenamiento

La fase de entrenamiento se materializó en el paquete
`mag7-risk-train-2021-2026-bf1`. Se alcanzó el límite de 120.000 relaciones únicas
artículo-empresa antes de completar todas las ventanas: 125 quedaron completas y
220 incompletas por presupuesto. Por tanto, el paquete es una adquisición acotada,
no un censo exhaustivo de noticias del periodo.

El filtro produjo un pool de 1.449 candidatos y la selección estratificada exportó
729 relaciones:

| Empresa | Pool de candidatos | Exportados | Objetivo | Déficit |
|---|---:|---:|---:|---:|
| AAPL | 437 | 200 | 200 | 0 |
| GOOGL | 349 | 200 | 200 | 0 |
| MSFT | 534 | 200 | 200 | 0 |
| NVDA | 129 | 129 | 200 | 71 |
| **Total** | **1.449** | **729** | **800** | **71** |

Los 729 exportados contienen 515 activaciones de `cybersecurity` y 235 de
`critical_suppliers`; una relación puede activar ambas. En cuanto a contenido, 605
relaciones disponen de texto completo, 75 de texto parcial y 49 solo de resumen.
Estas cifras describen la salida automática anterior a la revisión, no el número de
positivos reales de cada familia.

La ejecución se reanudó varias veces aprovechando la caché y registra 1.620 páginas
del proveedor sin reintentos. El límite inicial de 1.080 páginas era un límite por
invocación y no un contador acumulado entre reanudaciones. En consecuencia, no debe
afirmarse que esta adquisición respetó un máximo global de 1.080 páginas. La cifra
correcta para la trazabilidad del consumo es 1.620. Esta limitación operativa debe
corregirse o controlarse externamente antes de abrir validación o test.

La hoja derivada
`data/processed/eodhd_mag7/datasets/mag7-risk-train-2021-2026-bf1/risk_news_candidates_review.csv`
contiene las 729 relaciones en estado `pending`. Su SHA-256 es
`57d8c990f761f9306ac965bfbcfc725fe903aa2842bbe8aa41780b3a6d499382` y el
SHA-256 del CSV original de candidatos es
`3f515d33dd265581b91270bd7d80f1ccd8bafe907c7a4be1e2fd3f85f42fa349`.
La hoja no incluye cuerpos y su generación no modifica el artefacto original.

## Uso en el TFM

En la memoria debe describirse el sistema como un proceso en dos etapas:

1. **Recuperación automática de candidatos.** Reglas léxicas y contextuales buscan
   una cobertura amplia y conservan términos activadores y procedencia.
2. **Validación humana.** La persona revisora consulta el contenido disponible,
   decide la relevancia empresarial, confirma o corrige la familia y documenta el
   estado del riesgo y el ruido.

En consecuencia, no debe presentarse la precisión del filtro como rendimiento de un
clasificador entrenado ni las activaciones como etiquetas automáticas. Las métricas
anteriores a la revisión miden volumen recuperado; las métricas posteriores miden
precisión de candidatos sobre desarrollo. El rendimiento generalizable solo podrá
estimarse después de congelar reglas y abrir las particiones reservadas.

## Trazabilidad

El paquete original de candidatos conserva sus hashes de procedencia. Las
anotaciones se almacenan en una hoja derivada y no modifican el CSV original. Los
cuerpos de noticias no se copian a informes ni a artefactos versionables. Cada
paquete nuevo debe utilizar un `dataset_id` distinto y registrar configuración,
presupuesto, periodo, partición, hashes y limitaciones en su manifiesto.
