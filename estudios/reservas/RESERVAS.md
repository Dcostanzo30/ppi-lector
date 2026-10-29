# Reservas del BCRA: brutas y netas (método FMI, estimación propia)

Último balance semanal: **2026-10-23** (el BCRA lo publica con una semana de demora). En miles de millones de US$.

| | Último | Hace 4 balances | Fin de 2025 |
|---|---|---|---|
| Reservas brutas (BCRA) | 50,2 | 48,9 | 41,1 |
| − Encajes en dólares | 16,6 | 15,1 | 15,0 |
| − Swaps y otros pasivos (incluye China) | 23,8 | 23,8 | 24,6 |
| − Crédito neto del FMI desde 2025 | 14,2 | 15,0 | 14,0 |
| **= Netas método FMI** | -3,7 | -4,2 | -11,8 |
| Netas FMI a tipos del programa (oro a US$4.326) | -3,0 | -4,2 | -11,8 |
| − BOPREAL | 5,0 | 5,0 | 13,1 |
| − Depósitos del Gobierno | 6,8 | 7,5 | 4,8 |
| **= Netas ácidas** | -15,4 | -16,7 | -29,7 |

Fechas: hace 4 balances = 2026-09-23; fin de 2025 = 2025-12-31.

## Control contra los datos oficiales del FMI

| Fecha | FMI | Nuestra estimación | Diferencia | Uso |
|---|---|---|---|---|
| 2023-12-23 | -11,2 | -7,0 | 4,2 | validación |
| 2024-12-31 | -2,4 | -2,3 | 0,1 | calibración |
| 2025-12-31 | -11,7 | -11,8 | -0,1 | calibración |
| 2026-03-31 (oro a US$2.808, programa de ene-2025) | −12,9 (−2,4 − 10,5) | -13,6 | -0,7 | validación (aprox.) |

Ajuste de calibración: 0,76 (otros pasivos del FMI que el balance no muestra por separado: SEDESA, ALADI, repos de corto plazo, diferencias de valuación).

## Últimos 12 balances

| Fecha | Brutas | Netas FMI | Netas FMI (tipos programa) | Netas ácidas |
|---|---|---|---|---|
| 2026-10-23 | 50,2 | -3,7 | -3,0 | -15,4 |
| 2026-10-15 | 50,0 | -3,7 | -3,4 | -14,5 |
| 2026-10-07 | 49,1 | -4,2 | -3,8 | -15,7 |
| 2026-09-30 | 46,1 | -4,5 | -4,2 | -15,9 |
| 2026-09-23 | 48,9 | -4,2 | -4,2 | -16,7 |
| 2026-09-15 | 50,0 | -4,1 | -4,0 | -16,8 |
| 2026-09-07 | 50,7 | -3,7 | -3,8 | -16,6 |
| 2026-08-31 | 48,3 | -3,7 | -3,9 | -16,6 |
| 2026-08-23 | 50,7 | -3,6 | -4,2 | -16,9 |
| 2026-08-15 | 49,5 | -4,1 | -4,2 | -17,5 |
| 2026-08-07 | 49,5 | -4,5 | -4,5 | -18,5 |
| 2026-07-31 | 47,6 | -4,2 | -3,7 | -19,1 |

Notas: el FMI resta el swap con China completo, los encajes y su propio crédito desde 2025, y no resta los depósitos del Tesoro.
"Netas ácidas" además resta BOPREAL y los depósitos del Gobierno (que incluyen pesos, así que es una cota exigente).
El crédito del FMI es un supuesto cargado a mano en reservas.py (desembolsos y devoluciones); hay que actualizarlo en cada movimiento.
