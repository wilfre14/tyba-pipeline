# Insights y analítica de movimientos

Corte publicado: **T1**. Fecha de corte: **2026-09-25**.
Reporte generado en UTC: 2026-09-28T05:27:04+00:00.

Fuente: bronze.cargas, silver.movimientos, silver.cuarentena y gold.movimientos. Las cifras se calculan durante la ejecución; no son valores fijos del ejemplo.

## 1. Calidad y disponibilidad

Se recibieron 49,000 filas: 46,571 cumplen las reglas obligatorias (95.04%) y 2,429 están en cuarentena (4.96%). Gold contiene 3,000 clientes distintos.

| Motivo de cuarentena | Filas | % de cuarentena |
|---|---:|---:|
| monto_nulo_o_invalido | 1,440 | 59.28% |
| monto_negativo_revisar | 989 | 40.72% |

Una fila puede tener varios motivos: sus conteos no se suman para calcular la cuarentena.
Acción: revisar primero los motivos con mayor frecuencia y corregir sus valores en el sistema origen.

## 2. Cambios entre cortes

Comparación: T (2026-09-24) → T1 (2026-09-25).
Tasa válida anterior: 94.85%; actual: 95.04%. Variación: +0.20 puntos porcentuales.
Hay 13,199 filas nuevas (28.34% de Gold), 33,372 sin cambios y 14,051 eliminadas (29.63% de los válidos anteriores).
Acción: contrastar los eliminados con el origen; estos datos no permiten distinguir por sí solos una cancelación, una modificación o un registro que ahora incumple calidad.

La comparación usa los ocho campos normalizados. No hay ID de transacción: un cambio de contenido se representa como eliminado + nuevo; corregido queda en cero. Los conteos son filas, no transacciones únicas. Se recomienda solicitar un ID estable al origen.

## 3. Completitud en Gold

Descripción ausente: 4,251 (9.13%). Nombre comercial ausente: 7,743 (16.63%). Monto cero: 903 (1.94%).
Estos casos son aceptados por las reglas actuales. Los textos ausentes limitan la segmentación descriptiva. Acción: acordar con negocio su obligatoriedad antes de endurecer las reglas.

## 4. Distribución de movimientos vigentes

| Producto | Filas Gold | Participación |
|---|---:|---:|
| cuenta de ahorro | 5,893 | 12.65% |
| cdt | 5,868 | 12.60% |
| bonos | 5,861 | 12.59% |
| divisas | 5,816 | 12.49% |
| fondo de inversión | 5,808 | 12.47% |
| fondo de pensión | 5,785 | 12.42% |
| acciones | 5,770 | 12.39% |
| etf | 5,770 | 12.39% |

El producto con más filas es cuenta de ahorro: 12.65% del total. La participación mide frecuencia de filas; no representa rentabilidad ni activos administrados.

| Tipo | Filas Gold | Participación |
|---|---:|---:|
| entrada | 25,339 | 54.41% |
| salida | 21,232 | 45.59% |

Fechas de movimiento en Gold: 2024-09-15 a 2024-10-16. Son distintas de la fecha de corte asignada al archivo. No se infiere un flujo monetario neto porque no se especifica una moneda común.

## 5. Cuadratura y conclusión

Válidos del corte anterior reconstruidos: 33,372 sin cambios + 14,051 eliminados = 47,423.

| Control | Calculado | Esperado | Estado |
|---|---:|---:|---|
| Gold + cuarentena = recibido | 49,000 | 49,000 | OK |
| Nuevos + sin cambios = Gold | 46,571 | 46,571 | OK |
| Gold + eliminados = Silver movimientos | 60,622 | 60,622 | OK |

Gold publica únicamente filas vigentes que superaron las reglas obligatorias. Silver conserva los eliminados para trazabilidad y separa los rechazos en cuarentena. Las cuadraturas verifican volumen, no garantizan la veracidad de los datos de origen.
