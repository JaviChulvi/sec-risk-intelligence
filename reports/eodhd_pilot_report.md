# Piloto EODHD para noticias MAG7

Ejecución: `demo`; intervalo `2026-10-13` a `2026-10-19`.

## Alcance medido

- Artículos recuperados: 616.
- Identificadores únicos: 537.
- Llamadas HTTP consumidas al adquirir el caché: 3; en esta ejecución: 0; reintentos: 0.
- Ventanas completas: 3; fallidas: 0.
- Grupos duplicados propuestos: 82.
- Exceso de registros dentro de grupos duplicados: 117 (19.0%).
- Episodios propuestos para revisión: 17.
- Candidatos léxicos: 18; con texto `full` o `partial`: 18 (100.0%).
- Longitud mediana: 527.5 palabras.

## Calidad del contenido

- `full`: 414 (67.2%).
- `partial`: 21 (3.4%).
- `summary_only`: 181 (29.4%).
- `missing`: 0 (0.0%).
- `invalid`: 0 (0.0%).

## Viabilidad técnica inicial

- Almacenamiento restringido bruto: 2897153 bytes.
- Normalizados restringidos: 3490358 bytes.
- Derivados sin cuerpos: 652439 bytes.
- El mínimo teórico del histórico es de 9 llamadas por mes (nueve símbolos de consulta); la paginación, los reintentos y eventuales subdivisiones elevarán ese valor.

## Inspección cualitativa del smoke test

- El campo content contiene texto en los 616 registros demo, pero 181 son resúmenes breves y no texto suficiente de artículo.
- El elemento más corto inspeccionado terminaba con una invitación a continuar leyendo y quedó correctamente clasificado como summary_only; los elementos mediano y largo contenían prosa sustancial o texto similar a una transcripción.
- Los 18 candidatos léxicos tenían texto full o partial, pero muchos titulares trataban sobre otro emisor, comentarios generales de mercado, análisis de inversión o predicciones, no sobre un acontecimiento adverso que afectara a la empresa consultada.
- La sindicación entre empresas y la recuperación multiactivo producen una duplicación considerable; los recuentos de artículos no pueden tratarse como recuentos de acontecimientos.
- Estas observaciones son cualitativas y no deben presentarse como una tasa medida de ruido ni como precisión del filtro.

## Revisión completa de candidatos y muestra de contraste

- Filas revisadas: 33 de 33; la unidad es la relación artículo-empresa (29 artículos únicos).
- Estrato `risk_candidate`: 18 revisados, 0 relevantes y 18 no relevantes; tasa observada de relevancia: 0.0%.
- Al estar revisados los 18 candidatos, el 0.0% es el resultado completo de este smoke test, no una extrapolación desde la muestra.
- Cobertura de candidatos del smoke test: 18 de 18 (100.0%); quedan 0 sin revisar.
- Estrato de contraste `other`: 15 revisados y 0 relevantes.
- Causas de ruido entre candidatos revisados: `other_company`: 9, `prediction`: 1, `routine_news`: 1, `stock_analysis`: 7.
- La anotación figura como asistida por ChatGPT: es útil para diagnosticar reglas, pero no es un gold standard humano independiente ni una estimación estadística de precisión.

## Decisión provisional

**PENDIENTE** — el smoke test no mide recuperación de episodios conocidos

Esta ejecución no convierte artículos en acontecimientos confirmados ni utiliza sentimiento como etiqueta adversa. Una ausencia de resultados significa únicamente ausencia de evidencia localizada.

## Limitaciones pendientes

- Confirmar las anotaciones con revisión humana independiente y revisar duplicados y agrupaciones de episodios.
- Completar la referencia de 49 fichas antes de medir recuperación por episodio.
- Incorporar el manifiesto SEC para construir las ventanas posteriores a cada segundo 10-K.
- Verificar condiciones de conservación y redistribución antes del histórico 2021–2026.

