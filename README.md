# Movimientos financieros: modelo simplificado

Python + DuckDB + SQL. Esta versión crea exactamente **dos tablas físicas en silver** y **una tabla física en gold**. No crea vistas ni tablas adicionales en esas capas.

| Capa | Tabla | Contenido |
|---|---|---|
| Bronze | `bronze.cargas` | Manifiesto y trazabilidad de todos los archivos recibidos. |
| Silver | `silver.movimientos` | Movimientos válidos clasificados en el último corte, incluidos los eliminados respecto al anterior. |
| Silver | `silver.cuarentena` | Rechazos del último corte, conservando valores originales y motivos. |
| Gold | `gold.movimientos` | Movimientos válidos vigentes: excluye eliminados y cuarentena. |

Bronze conserva también las copias originales de cada Parquet en `data/output/bronze`. Las tablas auxiliares del procesamiento son temporales y desaparecen al cerrar la conexión.

## Estructura exacta de silver.movimientos

| Campo | Tipo | Descripción |
|---|---|---|
| id_cliente | VARCHAR | Identificador del cliente. |
| date | DATE | Fecha del movimiento normalizada. |
| product | VARCHAR | Producto normalizado. |
| type | VARCHAR | entrada o salida. |
| fund | VARCHAR | Fondo normalizado. |
| amount | DECIMAL(20,2) | Monto válido, mayor o igual a cero. |
| description | VARCHAR | Descripción opcional. |
| commercial_name | VARCHAR | Nombre comercial opcional. |
| estado | VARCHAR | nuevo, eliminado, sin_cambios o corregido. |
| fecha_corte | DATE | Fecha efectiva del corte recibido. |
| fecha_proceso | TIMESTAMP | Fecha y hora de ejecución, expresada en UTC. |

No se agregan `corte`, `orden`, `fila_origen` ni `motivos` a esta tabla. El manifiesto de bronze conserva la etiqueta T/T1 y su orden.

`silver.cuarentena` contiene los ocho campos de origen sin convertir, `motivos`, `fecha_corte` y `fecha_proceso`. Así una fecha inválida no se pierde convirtiéndola a NULL. `gold.movimientos` tiene la misma estructura que `silver.movimientos`, con los registros vigentes.

## Qué se conserva en cada ejecución

Silver y gold representan **el resultado del último corte procesado**. La publicación reemplaza esas tres tablas en una sola transacción. No se acumulan snapshots en ellas; el historial original permanece en bronze.

Bronze conserva todos los archivos y cargas para auditar o reconstruir cortes anteriores. Para comparar T2 se vuelve a normalizar el archivo original de T1; no se usan como entrada las filas marcadas como eliminadas en silver. Las cuarentenas históricas también se pueden reconstruir desde bronze.

Este modelo es más pequeño que el anterior. No contiene `silver.clasificacion`, `silver.comparacion`, `silver.diferencias` ni vistas gold. Los resúmenes se obtienen con consultas SQL cuando se necesitan.

## Fechas de corte

Las fechas proporcionadas por el usuario están configuradas como valores predeterminados:

| Archivo | Etiqueta | fecha_corte |
|---|---|---|
| movimientos_dia_T.parquet | T | 2026-09-24 |
| movimientos_dia_T1.parquet | T1 | 2026-09-25 |

`python src/pipeline.py` y `docker compose up --build` aplican esas fechas automáticamente. Después de T1, las tres tablas silver/gold muestran `fecha_corte = 2026-09-25`, pues representan el último corte. La fecha de T permanece registrada en `bronze.cargas`. `date` sigue siendo la fecha del movimiento de origen.

Para proporcionar otras fechas explícitamente en una reconstrucción:

```powershell
python src/pipeline.py --fecha-t AAAA-MM-DD --fecha-t1 AAAA-MM-DD --output data/output_con_fechas
```

Reemplazar los marcadores por las fechas reales. T1 debe ser posterior a T. Una base anterior con fechas NULL debe reconstruirse en una carpeta nueva; el ZIP actualizado se entrega sin base precargada para facilitar esa primera ejecución. `fecha_proceso` se completa con la fecha y hora efectiva de la carga en UTC y no se reemplaza por la fecha de corte. En una reejecución idempotente se conserva la fecha original de proceso.

Las cargas futuras con `--archivo` requieren `--fecha-corte` explícita.

## Calidad

Se mantienen las reglas acordadas:

- Cuarentena: monto NULL, no convertible, infinito/fuera de rango o negativo; fecha inválida; tipo desconocido; cliente, producto o fondo vacío.
- Normalización: fecha ISO o día/mes/año, espacios, mayúsculas de producto/fondo y equivalencias IN/OUT a entrada/salida.
- Se aceptan montos cero.
- Descripción y nombre comercial son opcionales. Su ausencia no provoca cuarentena y permanece como NULL.
- No se eliminan filas idénticas: sin ID de transacción no se puede distinguir duplicación accidental de movimientos legítimos repetidos.

Por tanto, «limpia» significa conforme a estas reglas de calidad, no necesariamente sin ningún NULL. La moneda no está identificada en el origen; cualquier agregado monetario oficial requiere confirmar que los importes comparten unidad.

## Clasificación por todos los campos

La llave es `(id_cliente,date,product,type,fund,amount,description,commercial_name)` después de normalizar. Se comparan directamente las ocho columnas mediante `EXCEPT ALL` e `INTERSECT ALL`, preservando repeticiones y equivalencia de NULL con NULL.

| Estado | Regla |
|---|---|
| nuevo | Aparece en el corte actual y no en el anterior, o aumenta su número de apariciones. |
| eliminado | Aparece en el corte anterior y no en el actual, o disminuye su número de apariciones. |
| sin_cambios | Coincide la fila completa en ambos cortes. |
| corregido | No es identificable con la llave completa; una modificación se representa como eliminado + nuevo. |

Los estados corresponden a contenido válido. Se excluyen los rechazos antes de comparar; un registro que cambia a valores inválidos queda en cuarentena y la llave válida anterior deja de aparecer como vigente. No significa que la transacción de negocio haya sido cancelada.

En la primera carga todos los válidos son nuevos. El estado eliminado se conserva en silver durante el corte que detecta la ausencia, pero no entra a gold. Las fechas de un eliminado corresponden al corte en el que se detectó su ausencia; `date` sigue siendo la fecha original del movimiento.

## Resultados de los archivos originales

| Medida | T | T1 |
|---|---:|---:|
| Filas recibidas | 50.000 | 49.000 |
| Válidas vigentes en gold | 47.423 | 46.571 |
| Cuarentena | 2.577 | 2.429 |
| Nuevos en silver | 47.423 | 13.199 |
| Sin cambios en silver | 0 | 33.372 |
| Eliminados en silver | 0 | 14.051 |
| Corregidos identificables | 0 | 0 |

Después de T1, `silver.movimientos` tiene **60.622 filas**, `silver.cuarentena` tiene **2.429** y `gold.movimientos` tiene **46.571**. Silver incluye 14.051 eliminados; por eso su conteo supera el volumen vigente.

Reconciliaciones:

```text
33.372 + 14.051 = 47.423 válidas anteriores
33.372 + 13.199 = 46.571 válidas actuales
46.571 +  2.429 = 49.000 filas recibidas en T1
```

Las cifras anteriores de 13.841 nuevos, 14.841 eliminados y 35.159 sin cambios incluían filas inválidas. No deben compararse directamente con los estados del nuevo silver limpio.

## Ejecutar

Desde esta carpeta, con Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe src/pipeline.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe src/consultar.py
```

El ZIP actualizado incluye código y los dos Parquet, sin base precargada: la primera ejecución construye las tablas. Ejecutar de nuevo no duplica filas ni vuelve a publicar T sobre T1. Para ejecutar desde cero otra vez sin borrar archivos:

```powershell
.\.venv\Scripts\python.exe src/pipeline.py --output data/output_practica
.\.venv\Scripts\python.exe src/consultar.py "SELECT count(*) FROM gold.movimientos" --db data/output_practica/movimientos.duckdb
```

Con Docker y Compose instalados:

```powershell
docker compose up --build
```

Ver `GUIA_DOCKER.md` para los pasos completos de instalación, ejecución, consultas y solución de errores en Windows/VS Code.

Los archivos originales del ejemplo se consideran cortes completos según el enunciado. Un corte nuevo requiere confirmación explícita:

```powershell
python src/pipeline.py --archivo data/raw/movimientos_dia_T2.parquet --corte T2 --orden 3 --fecha-corte AAAA-MM-DD --completo
```

Un archivo no vacío no demuestra completitud; `--completo` expresa que el operador la confirmó con el productor. La comparación solo permite inferir ausencias respecto a un corte completo.

## Código para leer en orden

1. `src/pipeline.py`: checksum, copia bronze, orden y fechas, preparación temporal y transacción.
2. `src/normalizar.sql`: reglas de formato y calidad.
3. `src/silver.sql`: las dos tablas físicas solicitadas.
4. `src/gold.sql`: la única tabla física de consumo.
5. `src/consultar.py`: consultas de solo lectura.

## Actualización desde la versión anterior

Descomprimir esta entrega en una carpeta nueva y abrir esa carpeta en VS Code. No reutilizar la base de versiones anteriores: contiene otras tablas y vistas. La nueva entrega reconstruye el modelo desde los dos Parquet originales y conserva la entrega anterior por separado.

Si existen cortes adicionales en otra instalación, volver a procesar sus archivos en orden sobre una base nueva, indicando sus fechas reales. El código rechaza cargar sobre la estructura anterior para evitar mezclar modelos.

## Verificación y límites

Se verifican estructura exacta, columnas, separación de rechazos, estados, multiplicidad, metadatos, nulos opcionales, reejecución, cortes fuera de orden, fechas inconsistentes, archivo cambiado, corte vacío y evolución T → T1 → T2.

La ejecución usa DuckDB directamente, dos hilos, buffer configurado a 512 MB y temporales en disco; el límite del buffer no equivale al máximo RSS del proceso. Python no acumula las filas en listas ni DataFrames. No se ha repetido la prueba de un millón de filas para esta versión; la medición anterior pertenece al modelo anterior.

Docker no está instalado en el entorno de preparación: se entrega su configuración, pero la verificación realizada es nativa. No se ha publicado un repositorio remoto ni instalado un programador diario.
