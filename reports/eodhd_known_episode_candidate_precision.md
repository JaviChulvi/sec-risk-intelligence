# Precisión del filtro en ventanas de episodios conocidos

## Resultado confirmado

- Candidatos relevantes: 20/51 (39.2%).
- Falsos positivos: 31/51 (60.8%).
- Candidatos relevantes con familia correcta: 10/51 (19.6%).
- Exactitud de familia entre candidatos relevantes: 50.0%.
- Contenido útil entre relevantes: 100.0%.
- Recall por episodio: 83.3%; recall con familia correcta: 83.3%.

## Por episodio

| Episodio | Candidatos | Relevantes | Precisión | Familia correcta |
|---|---:|---:|---:|---:|
| AAPL-2021-NSO-LAWSUIT | 6 | 1 | 16.7% | 1 |
| AAPL-2022-ZHENGZHOU | 8 | 4 | 50.0% | 3 |
| MSFT-2023-STORM-0558 | 9 | 3 | 33.3% | 3 |
| MSFT-2024-CROWDSTRIKE-OUTAGE | 14 | 10 | 71.4% | 1 |
| MSFT-2024-MIDNIGHT-BLIZZARD | 11 | 2 | 18.2% | 2 |
| TSLA-2023-IF-METALL | 3 | 0 | 0.0% | 0 |

## Interpretación

- No hay un umbral de precisión configurado; no se asigna automáticamente GO/NO_GO.
- Recall y precisión usan unidades distintas (episodios frente a artículos-empresa), por lo que no se calcula F1.
- Las métricas describen estas seis ventanas confirmadas y no estiman por sí solas el rendimiento del histórico completo.

