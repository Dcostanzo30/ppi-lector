# Diagnóstico A3 market data — 2026-11-17 21:50

- Cauciones 2026-06-01 a 2026-07-01: 63 filas
- Cauciones 2026-07-02 a 2026-08-01: 58 filas
- Cauciones 2026-08-02 a 2026-09-01: 58 filas
- Cauciones 2026-09-02 a 2026-10-02: 70 filas
- Cauciones 2026-10-03 a 2026-11-02: 60 filas
- Cauciones 2026-11-03 a 2026-11-17: 22 filas
  Columnas: ['fecha', 'montoConcertado', 'montoColocador', 'montoTomador', 'tasaColocador', 'tasaTomador', 'tasaPP', 'ticker', 'tipoEmision', 'fechaLiquidacion', 'volumen', 'monto', 'descripcion', 'plazo', 'codigoPlazo', 'segmento', 'codigoSegmento', 'moneda', 'variacion', 'ultimo', 'ultimaTasa', 'cierreAnterior', 'minimo', 'maximo', 'openInterest', 'precioCierre', 'precioApertura', 'fecha_dia', 'volumen_dia']
  Ejemplo: {"fecha": "2026-07-01T00:00:00", "montoConcertado": 302481633.0, "montoColocador": 0, "montoTomador": 0, "tasaColocador": 0, "tasaTomador": 0, "tasaPP": 1.9981, "ticker": "CAUSD", "tipoEmision": "CAU", "fechaLiquidacion": "2026-07-02T00:00:00", "volumen": 0, "monto": 0, "descripcion": "CAUSD D 001", "plazo": "001", "codigoPlazo": null, "segmento": "K", "codigoSegmento": null, "moneda": "D", "varia
- resumen/DDF: 14 filas
  Ejemplo: {"ticker": "DLR022027", "tipoEmision": "DDF", "descripcion": "DLR022027", "plazo": "---", "fechaLiquidacion": null, "moneda": "", "segmento": "DDF", "variacion": 0.2114, "ultimo": 1660.5, "cantidad": 5624.0, "monto": 9319926000.0, "codigoOrden": null, "tickerOrden": null, "tipoNegociacion": null, "c
- datos/DER: 0 filas  <- sin operaciones
- datos/FOR: 14 filas
  Ejemplo: {"ticker": "EB$T", "tipoEmision": "FOR", "fechaLiquidacion": "0001-01-01T00:00:00", "volumen": 25000, "monto": 43650000, "descripcion": "EB$T  (EURO BILL. A PESO TR.)", "plazo": "000", "codigoPlazo": "000", "segmento": "Minorista", "codigoSegmento": "N", "moneda": "T", "variacion": 0.0, "ultimo": 17
  - datos/DDF: HTTP 500
  - datos/DDF: HTTP 500
  - datos/DDF: HTTP 500
- datos/DDF: 0 filas
- volumen-categoria: 12 filas; categorías: ['Cauciones', 'FOREX', 'Futuro de Dólar', 'REPO', 'Renta Fija PPT', 'Renta Fija TRD']