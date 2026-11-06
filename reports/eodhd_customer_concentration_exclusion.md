# Decisión sobre `customer_concentration` en noticias EODHD

Fecha de consolidación: 2026-10-30.

## Decisión

Se excluye `customer_concentration` como clase objetivo del
dataset principal de noticias EODHD. El dataset de noticias se centrará en
`cybersecurity` y `critical_suppliers`. Las activaciones de estas dos familias
siguen sujetas a revisión humana antes de convertirse en etiquetas del dataset.

Esta decisión afecta únicamente al experimento basado en noticias. No elimina
`customer_concentration` de la taxonomía de riesgos ni del análisis de los
`10-K`, donde sigue siendo un riesgo empresarial válido y potencialmente
relevante. Tampoco se borran sus reglas, candidatos o evidencias históricas:
se conservan para trazabilidad y análisis exploratorio.

## Evidencia

### Desarrollo del filtro

En el corpus local etiquetado, el filtro anterior produjo 13 activaciones de
`customer_concentration` y las 13 fueron incorrectas. Los términos observados
mostraron el siguiente comportamiento:

| Término | Activaciones | Falsos positivos | Precisión observada |
|---|---:|---:|---:|
| `major customer` | 8 | 7 | 12,5 % |
| `key customer` | 4 | 4 | 0,0 % |
| `customer concentration` | 2 | 2 | 0,0 % |

Las activaciones por término pueden solaparse en una misma relación. Tras la
revisión de reglas no quedó ninguna activación de esta familia y no existe
ningún positivo etiquetado que permita validar su comportamiento. La precisión
de la tabla por término mide selección de noticias de riesgo; no confirma que
la familia propuesta fuera correcta. De hecho, las 13 asignaciones de familia
`customer_concentration` fueron incorrectas.

Fuente: `reports/eodhd_risk_news_development.md`.

### Episodios de referencia

El inventario auditado no contiene ningún episodio independiente y elegible de
`customer_concentration`. Por tanto, la recuperación de esta familia no pudo
medirse en el benchmark de episodios conocidos.

Fuentes:

- `reports/eodhd_reference_filter_report.md`;
- `reports/eodhd_known_episode_recovery.md`.

### Adquisición amplia de entrenamiento

La adquisición *breadth-first* de enero a septiembre de 2026 examinó 9.861
relaciones únicas artículo-empresa y produjo 57 candidatos:

| Familia | Candidatos léxicos |
|---|---:|
| `cybersecurity` | 36 |
| `critical_suppliers` | 16 |
| `customer_concentration` | 5 |

Los cinco candidatos de `customer_concentration` representan aproximadamente
el 0,05 % de las relaciones admitidas. La revisión humana estructurada confirmó
solo uno como `customer_concentration`; otro era una noticia de riesgo válida,
pero correspondía a `critical_suppliers`, y los tres restantes fueron falsos
positivos. La precisión de familia observada fue por tanto 1/5, o 20,0 %.

Fuentes:

- `data/processed/eodhd_mag7/datasets/mag7-risk-train-2026-bf1/dataset_manifest.json`;
- `data/processed/eodhd_mag7/datasets/mag7-risk-train-2026-bf1/risk_news_candidates_review.csv`.

## Justificación metodológica

`customer_concentration` suele ser una exposición estructural —dependencia de
uno o varios clientes relevantes— y no necesariamente un acontecimiento
noticioso puntual. Los `10-K`, las cuentas anuales y determinadas publicaciones
financieras son fuentes más naturales para observarla que una recuperación
general de noticias por ticker.

Mantenerla como clase entrenable con la evidencia actual introduciría tres
problemas:

1. una clase extremadamente minoritaria, sin volumen suficiente para dividirla
   entre entrenamiento, validación y test;
2. ausencia de positivos confirmados y de episodios de referencia con los que
   estimar precisión o recuperación;
3. riesgo de enseñar al modelo patrones de ruido léxico en lugar de una señal
   real de concentración de clientes.

La exclusión no resuelve por sí sola el problema general de volumen: el paquete
amplio pasa de 57 a 52 candidatos al retirar esta familia. Será necesario revisar
la precisión de `cybersecurity` y `critical_suppliers` y mejorar la recuperación
antes de considerar alcanzable el tamaño objetivo del dataset.

## Alcance y condiciones para reconsiderarla

La decisión podrá revisarse únicamente con evidencia nueva
obtenida sobre el conjunto de entrenamiento, sin usar validación ni test para
ajustar reglas. Para reabrir la clase hará falta:

- una estrategia de búsqueda dirigida y predefinida, adecuada para exposiciones
  estructurales y no solo para noticias episódicas;
- una muestra humana con suficientes positivos confirmados para sostener una
  partición y una evaluación separadas;
- precisión y relevancia empresarial demostrables, no solo coincidencias con
  términos como `major customer` o `key customer`;
- congelar después las reglas antes de consultar validación o test.

Hasta que se cumplan estas condiciones, los cinco candidatos existentes se
mantienen como material exploratorio y no como ejemplos de una clase entrenable.

