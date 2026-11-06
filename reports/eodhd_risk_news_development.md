# Métricas de desarrollo del filtro de noticias de riesgo

## Resultado

- Filtro almacenado: 20/69 positivos (29.0% de precisión de desarrollo).
- Filtro revisado: 70/98 positivos (71.4% de precisión en el corpus local etiquetado).
- Cobertura de positivos en la unión de candidatos: 70/71 (98.6%).
- Falsos positivos retenidos: 28 frente a 49 en el filtro almacenado.
- Familia correcta entre positivos seleccionados: 50.0% → 97.1%.
- Evidencia conservada: 5/5 episodios recuperados.
- Estrato de candidatos nuevos: 51/75 positivos (68.0%).
- Confusiones de familia restantes: `cybersecurity->critical_suppliers`: 2.

## Diagnóstico de falsos positivos

### Por familia

| Familia | Activaciones anteriores | Incorrectas antes | Activaciones revisadas | Incorrectas ahora |
|---|---:|---:|---:|---:|
| `critical_suppliers` | 22 | 18 | 56 | 17 |
| `customer_concentration` | 13 | 13 | 0 | 0 |
| `cybersecurity` | 36 | 30 | 42 | 13 |

### Por empresa

| Empresa | FP anteriores | FP revisados | Positivos retenidos |
|---|---:|---:|---:|
| `AAPL` | 15 | 9 | 27/28 |
| `AMZN` | 6 | 0 | 0/0 |
| `MSFT` | 19 | 18 | 43/43 |
| `TSLA` | 9 | 1 | 0/0 |

### Por tipo de ruido

| Tipo | Etiquetados | Seleccionados antes | Seleccionados ahora |
|---|---:|---:|---:|
| `off_topic` | 55 | 31 | 28 |
| `other_company` | 9 | 9 | 0 |
| `prediction` | 1 | 1 | 0 |
| `routine_news` | 1 | 1 | 0 |
| `stock_analysis` | 7 | 7 | 0 |

### Términos anteriores con más falsos positivos

| Término | Activaciones | Falsos positivos | Precisión |
|---|---:|---:|---:|
| `cybersecurity:cyberattack` | 31 | 16 | 48.4% |
| `critical_suppliers:supply disruption` | 18 | 14 | 22.2% |
| `customer_concentration:major customer` | 8 | 7 | 12.5% |
| `customer_concentration:key customer` | 4 | 4 | 0.0% |
| `critical_suppliers:critical supplier` | 2 | 2 | 0.0% |
| `customer_concentration:customer concentration` | 2 | 2 | 0.0% |
| `cybersecurity:data breach` | 2 | 2 | 0.0% |
| `critical_suppliers:cloud provider outage` | 1 | 1 | 0.0% |
| `critical_suppliers:sole supplier` | 1 | 1 | 0.0% |
| `cybersecurity:ransomware` | 4 | 1 | 75.0% |
| `cybersecurity:unauthorized access` | 2 | 1 | 50.0% |

## Reprocesado local

Se evaluaron 2360 relaciones artículo-empresa de las cachés locales, sin llamadas de red.

- Candidatos almacenados: 69.
- Candidatos con las reglas revisadas: 98.
- Candidatos retenidos/nuevos/eliminados: 23/75/46.
- Candidatos revisados sin ninguna etiqueta: 0.

## Interpretación

Las 75 etiquetas nuevas se añadieron después de fijar las reglas y completan la revisión de los 98 candidatos del filtro revisado en estas cachés. La comparación sigue sin ser un holdout temporal independiente y no estima el recall sobre noticias que ninguno de los dos filtros seleccionó.
No hay positivos etiquetados de `customer_concentration`; su comportamiento no puede validarse con este conjunto.

Las noticias posteriores al 10-K se mantienen como contraste exploratorio y no construyen las etiquetas de pérdida documental entre informes anuales.
