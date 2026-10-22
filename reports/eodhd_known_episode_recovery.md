# Recuperación de episodios conocidos en EODHD

## Métricas confirmadas

- Recuperación: 5/6 (83.3%).
- Recuperación con contenido útil: 5/5 (100.0%).
- Recuperación con familia automática correcta: 5/6 (83.3%).
- Umbral numérico configurado: `GO`.

## Resultado por episodio

| Episodio | Familia | Recuperado | Familia correcta | Contenido útil |
|---|---|---:|---:|---:|
| AAPL-2021-NSO-LAWSUIT | cybersecurity | sí | sí | sí |
| AAPL-2022-ZHENGZHOU | critical_suppliers | sí | sí | sí |
| MSFT-2023-STORM-0558 | cybersecurity | sí | sí | sí |
| MSFT-2024-CROWDSTRIKE-OUTAGE | critical_suppliers | sí | sí | sí |
| MSFT-2024-MIDNIGHT-BLIZZARD | cybersecurity | sí | sí | sí |
| TSLA-2023-IF-METALL | critical_suppliers | no | no | no |

## Límites

- customer_concentration no tiene ningún episodio de referencia elegible.
- El benchmark confirmado contiene solo seis episodios independientes.
- IF Metall no fue recuperado por EODHD en la ventana evaluada.
