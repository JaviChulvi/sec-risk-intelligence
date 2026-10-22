# Filtrado de episodios conocidos para el piloto EODHD

## Resultado

- Fichas auditadas: 49.
- Episodios independientes elegibles: 6.
- Fichas de seguimiento agrupadas: 1.
- Fichas excluidas: 42.

## Cobertura por familia

- `critical_suppliers`: 3 episodios.
- `customer_concentration`: 0 episodios.
- `cybersecurity`: 3 episodios.

## Episodios candidatos

| Episodio | Empresa | Familia | t0 | Ventana | Fichas |
|---|---|---|---|---|---|
| AAPL-2021-NSO-LAWSUIT | AAPL | cybersecurity | 2021-10-29 | 2021-10-29–2022-10-29 | AAPL-01 |
| MSFT-2023-STORM-0558 | MSFT | cybersecurity | 2022-07-28 | 2022-07-28–2023-07-28 | MSFT-04, MSFT-08 |
| AAPL-2022-ZHENGZHOU | AAPL | critical_suppliers | 2022-10-28 | 2022-10-28–2023-10-28 | AAPL-02 |
| TSLA-2023-IF-METALL | TSLA | critical_suppliers | 2023-01-31 | 2023-01-31–2024-01-31 | TSLA-05 |
| MSFT-2024-CROWDSTRIKE-OUTAGE | MSFT | critical_suppliers | 2023-07-27 | 2023-07-27–2024-07-27 | MSFT-07 |
| MSFT-2024-MIDNIGHT-BLIZZARD | MSFT | cybersecurity | 2023-07-27 | 2023-07-27–2024-07-27 | MSFT-05 |

## Exclusiones

- `excluded_out_of_scope_family`: 40. La ficha no describe un episodio perteneciente a customer_concentration, critical_suppliers o cybersecurity sin ampliar artificialmente la taxonomía.
- `excluded_outside_window`: 1. La noticia conocida es de 2022-03-01, tres días posterior al final estricto de la ventana 2021-02-26 a 2022-02-26.
- `excluded_unverifiable_event_date`: 1. La noticia describe prácticas históricas sin una fecha de acontecimiento concreta y verificable; la fecha de publicación no sustituye esa evidencia.

## Limitaciones

- Las decisiones son candidatas asistidas por ChatGPT y requieren confirmación humana independiente.
- El inventario no aporta un episodio elegible de `customer_concentration`; no puede afirmarse cobertura de las tres familias.
- Este filtrado no consulta EODHD ni mide recuperación.

