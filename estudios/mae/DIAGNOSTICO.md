# Diagnóstico A3 market data — 2026-11-13 22:25

- Cauciones 2026-06-01 a 2026-07-01: 63 filas
- Cauciones 2026-07-02 a 2026-08-01: 58 filas
- Cauciones 2026-08-02 a 2026-09-01: 58 filas
- Cauciones 2026-09-02 a 2026-10-02: 70 filas
- Cauciones 2026-10-03 a 2026-11-02: 60 filas
- Cauciones 2026-11-03 a 2026-11-13: 18 filas
  Columnas: ['fecha', 'montoConcertado', 'montoColocador', 'montoTomador', 'tasaColocador', 'tasaTomador', 'tasaPP', 'ticker', 'tipoEmision', 'fechaLiquidacion', 'volumen', 'monto', 'descripcion', 'plazo', 'codigoPlazo', 'segmento', 'codigoSegmento', 'moneda', 'variacion', 'ultimo', 'ultimaTasa', 'cierreAnterior', 'minimo', 'maximo', 'openInterest', 'precioCierre', 'precioApertura', 'fecha_dia', 'volumen_dia']
  Ejemplo: {"fecha": "2026-07-01T00:00:00", "montoConcertado": 302481633.0, "montoColocador": 0, "montoTomador": 0, "tasaColocador": 0, "tasaTomador": 0, "tasaPP": 1.9981, "ticker": "CAUSD", "tipoEmision": "CAU", "fechaLiquidacion": "2026-07-02T00:00:00", "volumen": 0, "monto": 0, "descripcion": "CAUSD D 001", "plazo": "001", "codigoPlazo": null, "segmento": "K", "codigoSegmento": null, "moneda": "D", "varia
- resumen/DDF: 13 filas
  Ejemplo: {"ticker": "DLR112026", "tipoEmision": "DDF", "descripcion": "DLR112026", "plazo": "---", "fechaLiquidacion": null, "moneda": "", "segmento": "DDF", "variacion": -0.1278, "ultimo": 1562.5, "cantidad": 517575.0, "monto": 809413214500.0, "codigoOrden": null, "tickerOrden": null, "tipoNegociacion": nul
- datos/DER: 0 filas  <- sin operaciones
- datos/FOR: 18 filas
  Ejemplo: {"ticker": "CHB$T", "tipoEmision": "FOR", "fechaLiquidacion": "0001-01-01T00:00:00", "volumen": 413000, "monto": 598850, "descripcion": "CHB$T  (P. CHILENO BILL A PESOS TRANS)", "plazo": "000", "codigoPlazo": "000", "segmento": "Minorista", "codigoSegmento": "N", "moneda": "T", "variacion": -12.1212
  - datos/DDF: HTTP 500
  - datos/DDF: HTTP 500
  - datos/DDF: HTTP 500
- datos/DDF: 0 filas
- volumen-categoria: 12 filas; categorías: ['Cauciones', 'FOREX', 'Futuro de Dólar', 'REPO', 'Renta Fija PPT', 'Renta Fija TRD']