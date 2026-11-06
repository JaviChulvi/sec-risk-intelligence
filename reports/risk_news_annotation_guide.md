# Guía breve de anotación de noticias de riesgo

**Versión:** 1.0 · **Unidad de anotación:** relación noticia–empresa ·
**Archivo:** `risk_news_candidates_review.csv`

## Objetivo

Decidir si una noticia describe un riesgo, exposición o acontecimiento adverso real
para la empresa indicada y, en caso afirmativo, confirmar la familia correcta. El
filtro solo propone candidatos: una coincidencia léxica o la familia sugerida no son
una etiqueta válida por sí solas.

La noticia debe evaluarse de forma independiente. **No consultar el 10-K asociado**
durante esta fase, para no condicionar la decisión. No editar las columnas comprendidas
entre `review_order` y `link`, que contienen la procedencia del candidato.

## Decisión por fila

1. Leer el título y el contenido disponible. Si el título no basta, abrir `link` o
   consultar el cuerpo en la caché restringida.
2. Comprobar que el hecho afecta o expone realmente a la empresa de la fila. No basta
   con que esta aparezca mencionada como cliente, proveedor, competidor o ejemplo.
3. Decidir `relevant_risk_news`:

   - `true`: existe un riesgo o hecho adverso concreto y suficientemente respaldado;
   - `false`: es ruido, otra empresa, una coincidencia ambigua o una mención sin
     exposición material;
   - si la evidencia no permite decidir, **no forzar la etiqueta**: mantener
     `review_status: pending` y remitir el caso al grupo.

4. Si es positiva, confirmar una o ambas familias y asignar `event_status`.
5. Si es negativa, dejar vacíos los campos positivos y seleccionar un `noise_type`.
6. Completar `reviewer`, `notes` y, solo entonces, poner `review_status: reviewed`.

## Familias y estado del riesgo

| Campo | Criterio |
|---|---|
| `cybersecurity` | Ataque, intrusión, *ransomware*, malware, acceso no autorizado, filtración o incidente de seguridad que afecte o exponga de manera concreta a la empresa, sus sistemas, datos, productos o usuarios. No incluye por sí sola privacidad, regulación, litigios o venta de productos de seguridad. |
| `critical_suppliers` | Dependencia o fallo material de un proveedor, fabricante, componente, servicio cloud, software crítico u otra dependencia externa; incluye escasez, interrupción, cierre, actualización defectuosa o capacidad restringida con vínculo concreto con la empresa. No basta una escasez sectorial genérica. |
| `materialized` | El incidente o impacto ya ha ocurrido. |
| `exposure` | Existe una dependencia o vulnerabilidad real, aunque todavía no se haya materializado el daño. |
| `emerging` | Amenaza nueva y respaldada por hechos que está desarrollándose; no una hipótesis genérica. |

En `confirmed_risk_families`, usar exactamente `cybersecurity`,
`critical_suppliers` o `cybersecurity|critical_suppliers`. La familia confirmada
puede diferir de `proposed_risk_families`.

## Cómo completar los campos

| Resultado | Campos obligatorios |
|---|---|
| Positivo | `relevant_risk_news=true`; `company_relevance=true`; `event_status`; `confirmed_risk_families`; `reviewer`; `notes`. Dejar `noise_type` vacío. |
| Negativo | `relevant_risk_news=false`; `company_relevance=true`, `false` o `unclear`; `noise_type`; `reviewer`; `notes`. Dejar vacíos `event_status` y `confirmed_risk_families`. |

### Cómo usar `company_relevance`

Este campo responde únicamente a «¿el contenido atribuye el hecho o la exposición a
la empresa de esta fila?». No responde a si el hecho pertenece a una familia objetivo:

- `true`: la empresa es protagonista, afectada o está expuesta de forma concreta;
- `false`: solo se menciona o el riesgo corresponde realmente a otra empresa;
- `unclear`: el contenido no permite establecer con seguridad la relación empresarial.

Por tanto, `company_relevance=true` y `relevant_risk_news=false` es una combinación
válida: por ejemplo, una promoción de un producto de seguridad de la empresa sin
incidente adverso. `company_relevance=false` y `relevant_risk_news=false` corresponde
a noticias sobre otra empresa o a una relación comercial invertida. Toda fila positiva
debe tener `company_relevance=true`. Si existe un posible riesgo pero no puede
determinarse si afecta a la empresa, mantener la fila `pending` y escalarla al grupo.

### Cómo usar `event_status`

Se completa únicamente cuando `relevant_risk_news=true` y describe el grado de
materialización del hecho principal de la noticia:

- `materialized`: el incidente o impacto ya ocurrió; por ejemplo, una brecha
  confirmada o una interrupción que ya afecta a producción o servicio;
- `exposure`: existe una dependencia o vulnerabilidad concreta y actual, pero no se
  describe todavía un incidente o daño;
- `emerging`: aparece una amenaza nueva, creíble y específica para la empresa que
  está desarrollándose, sin impacto materializado aún.

Aplicar este orden: si el impacto ya ocurrió, usar `materialized`; si no ocurrió pero
hay una exposición estructural actual, usar `exposure`; solo usar `emerging` para una
amenaza nueva respaldada por hechos. Una predicción o posibilidad genérica no es
`emerging`: debe anotarse como negativa (`hypothetical`). Si una noticia materializada
también revela una exposición subyacente, elegir `materialized` y explicar la
exposición secundaria en `notes`. Las filas negativas dejan `event_status` vacío.

Tipos de ruido recomendados: `other_company`, `wrong_relationship_direction`,
`sector_level_only`, `product_or_service_promotion`, `stock_analysis`,
`recommendation_widget`, `regulatory_not_cyber`, `legal_not_cyber`,
`privacy_compliance_not_cyber`, `hypothetical`, `contextual_mention_insufficient`,
`lexical_ambiguity`, `wrong_risk_family` y `demand_not_supplier_failure`. Si ninguno
encaja, acordar una categoría con el grupo antes de crear un valor nuevo.

Usar `recommendation_widget` cuando la coincidencia proceda de titulares, enlaces o
bloques automáticos como «Most Read», «Related Articles» o «Recommended», y no del
contenido principal de la noticia.

En `notes`, escribir una justificación breve, por ejemplo: «La noticia confirma una
interrupción del proveedor X que reduce la producción de la empresa; exposición
materializada de `critical_suppliers`». No copiar cuerpos completos ni información
de los 10-K.

## Casos que suelen ser negativos

- La noticia trata principalmente de otra empresa y la empresa objetivo solo aparece
  mencionada.
- Se invierte la relación comercial: ser cliente importante de un proveedor no prueba
  concentración de clientes ni fallo de suministro para la empresa objetivo.
- Se anuncia un producto o servicio de ciberseguridad, pero no hay incidente ni
  exposición concreta.
- El asunto es regulatorio, legal, de privacidad o competencia, sin componente de
  ciberseguridad.
- Es análisis bursátil, recomendación de inversión, predicción o módulo editorial.
- Existe una escasez sectorial, pero no se demuestra un efecto o dependencia material
  para la empresa.

Las publicaciones duplicadas o sindicadas **no son negativos** por ser duplicadas:
deben recibir la misma decisión semántica y controlarse después mediante los grupos
de duplicados o eventos.

## Muestra común de calibración

La calibración utiliza 40 noticias seleccionadas de forma reproducible con la
semilla `mag7-risk-calibration-2021-2026-v1`: 10 por empresa, 20 por cada familia
designada, representación de 2021-2026, 25 textos completos, 8 parciales, 7 solo
resumen y 16 relaciones pertenecientes a grupos de duplicados.

Javi, Hugo e Higinio disponen de copias separadas con las mismas noticias y el mismo
orden: `calibration_sample_40_javi.csv`, `calibration_sample_40_hugo.csv` y
`calibration_sample_40_higinio.csv`. Cada miembro debe anotar únicamente su archivo,
sin consultar los demás. La selección y sus hashes están registrados en
`calibration_sample_40_manifest.json`.

## Control de calidad del grupo

Antes de repartir el archivo, todos los miembros deben anotar de forma independiente
las mismas 30–50 filas. Después se comparan discrepancias, se aclara esta guía y se
resuelven los casos por consenso. Una muestra del 10–20 % debería recibir doble
anotación. La decisión final de una fila considerada *gold* debe quedar confirmada
por una persona; las etiquetas generadas únicamente por IA deben identificarse como
*silver labels*.
