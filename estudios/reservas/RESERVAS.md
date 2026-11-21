# Reservas del BCRA: brutas y netas (método FMI, estimación propia)

Último balance semanal: **2026-11-15** (el BCRA lo publica con una semana de demora). En miles de millones de US$.

| | Último | Hace 4 balances | Fin de 2025 |
|---|---|---|---|
| Reservas brutas (BCRA) | 49,6 | 50,0 | 41,1 |
| − Encajes en dólares | 17,1 | 16,6 | 15,0 |
| − Swaps y otros pasivos (incluye China) | 24,0 | 23,7 | 24,6 |
| − Crédito neto del FMI desde 2025 | 14,2 | 14,2 | 14,0 |
| **= Netas método FMI** | -5,0 | -3,7 | -11,8 |
| Netas FMI a tipos del programa (oro a US$4.326) | -4,1 | -3,4 | -11,8 |
| − BOPREAL | 4,9 | 5,0 | 13,1 |
| − Depósitos del Gobierno | 3,5 | 5,8 | 4,8 |
| **= Netas ácidas** | -13,3 | -14,5 | -29,7 |

Fechas: hace 4 balances = 2026-10-15; fin de 2025 = 2025-12-31.

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
| 2026-11-15 | 49,6 | -5,0 | -4,1 | -13,3 |
| 2026-11-07 | 49,6 | -4,6 | -4,1 | -14,1 |
| 2026-10-31 | 48,6 | -3,8 | -3,0 | -15,5 |
| 2026-10-23 | 50,2 | -3,7 | -3,0 | -15,4 |
| 2026-10-15 | 50,0 | -3,7 | -3,4 | -14,5 |
| 2026-10-07 | 49,1 | -4,2 | -3,8 | -15,7 |
| 2026-09-30 | 46,1 | -4,5 | -4,2 | -15,9 |
| 2026-09-23 | 48,9 | -4,2 | -4,2 | -16,7 |
| 2026-09-15 | 50,0 | -4,1 | -4,0 | -16,8 |
| 2026-09-07 | 50,7 | -3,7 | -3,8 | -16,6 |
| 2026-08-31 | 48,3 | -3,7 | -3,9 | -16,6 |
| 2026-08-23 | 50,7 | -3,6 | -4,2 | -16,9 |

## Proyección a fin de año contra la meta del FMI

Meta de reservas netas de fin de diciembre (tipos del programa): **-4,1**. Último balance: 2026-11-15 con -4,09.

| Paso | Miles de millones de US$ |
|---|---|
| Netas del último balance (2026-11-15) | -4,09 |
| + Compras del BCRA ya publicadas después del balance (hasta 2026-11-17) | 0,11 |
| + Pagos comprometidos que bajan las netas () | 0,00 |
| + Resto (lo que se fue por otros lados): -0,229 por semana × 6,3 semanas | -1,44 |
| **= Netas a fin de año si el BCRA no compra más** | **-5,42** |
| Netas a fin de año al ritmo de compras de las últimas 8 semanas (0,223 por semana) | -4,02 |

**Para llegar a la meta, el BCRA tiene que comprar unos US$ 211 millones por semana** de acá a fin de año (viene comprando US$ 223 millones por semana). Al ritmo actual llega.

El "resto" junta todo lo que no son compras: pagos a otros organismos, BOPREAL, encajes, valuación del oro. Se estima con las últimas 8 semanas y cambia cada jueves. Los desembolsos y devoluciones de capital al FMI no mueven las netas (cambian igual reservas y crédito del FMI); los intereses sí.

Notas: el FMI resta el swap con China completo, los encajes y su propio crédito desde 2025, y no resta los depósitos del Tesoro.
"Netas ácidas" además resta BOPREAL y los depósitos del Gobierno (que incluyen pesos, así que es una cota exigente).
El crédito del FMI es un supuesto cargado a mano en reservas.py (desembolsos y devoluciones); hay que actualizarlo en cada movimiento.
