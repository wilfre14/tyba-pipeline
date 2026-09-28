# Ejecutar el proyecto con Docker Compose en Windows y VS Code

## 1. Preparar Docker

Instalar Docker Desktop siguiendo la [guía oficial para Windows](https://docs.docker.com/desktop/setup/install/windows-install/). Usar el motor de contenedores Linux con WSL 2. Si el instalador pide habilitar/actualizar WSL o reiniciar Windows, completar ese paso. Después abrir Docker Desktop y esperar a que el motor esté iniciado.

Abrir una terminal nueva de PowerShell y comprobar:

```powershell
docker --version
docker compose version
docker info
```

Los dos primeros deben mostrar versiones; `docker info` debe mostrar información del servidor sin error de conexión. Esta ruta no requiere instalar Python ni DuckDB en Windows: se instalan dentro de la imagen.

## 2. Descomprimir y abrir el proyecto

Descomprimir `tyba_medallion_fechas.zip` en una carpeta nueva. En VS Code, seleccionar **Archivo > Abrir carpeta** y abrir `tyba_medallion_v3`, la carpeta donde están `Dockerfile` y `docker-compose.yml`.

No superponer el contenido sobre la base vieja con fechas NULL. El ZIP actualizado incluye los Parquet y el código; la base se genera al ejecutar.

Estructura mínima:

```text
tyba_medallion_v3/
  Dockerfile
  docker-compose.yml
  requirements.txt
  src/
    pipeline.py
    normalizar.sql
    silver.sql
    gold.sql
    consultar.py
  data/
    raw/
      movimientos_dia_T.parquet
      movimientos_dia_T1.parquet
    output/
```

En VS Code, abrir **Terminal > Nueva terminal**. Comprobar que se está en la carpeta correcta:

```powershell
Get-Location
Get-ChildItem
Test-Path .\data\raw\movimientos_dia_T.parquet
Test-Path .\data\raw\movimientos_dia_T1.parquet
```

Los dos `Test-Path` deben devolver `True`.

## 3. Validar configuración y ejecutar

```powershell
docker compose config --quiet
docker compose up --build
```

El primer comando comprueba la configuración. El segundo construye la imagen, instala DuckDB y ejecuta el pipeline. La primera construcción necesita conexión a Internet para descargar Python y DuckDB. El comportamiento de `up --build` está descrito en la [referencia oficial de Compose](https://docs.docker.com/reference/cli/docker/compose/up/).

El script utiliza automáticamente:

```text
T  -> 2026-09-24
T1 -> 2026-09-25
```

No hay que editar el YAML ni pasar fechas por la terminal. Los logs esperados incluyen:

```text
T: recibidas=50000, vigentes válidas=47423, cuarentena=2577
T1: recibidas=49000, vigentes válidas=46571, cuarentena=2429
```

El contenedor termina porque es un proceso batch, no un servidor. Debe mostrar `exited with code 0`. Comprobar su estado:

```powershell
docker compose ps -a
docker compose logs pipeline
```

Para una ejecución en la que PowerShell reciba específicamente el código de salida del pipeline, usar en lugar del comando anterior:

```powershell
docker compose up --build --exit-code-from pipeline
$LASTEXITCODE
```

El resultado esperado es `0`.

## 4. Comprobar las fechas y resultados

Los siguientes comandos funcionan aunque el contenedor principal haya terminado, porque crean un contenedor temporal con la misma imagen y los mismos volúmenes:

```powershell
docker compose run --rm pipeline python src/consultar.py "SELECT corte, fecha_corte, filas, fecha_proceso FROM bronze.cargas ORDER BY orden"
```

Resultado esperado en el manifiesto:

| corte | fecha_corte | filas |
|---|---|---:|
| T | 2026-09-24 | 50.000 |
| T1 | 2026-09-25 | 49.000 |

Inventario de las tablas:

```powershell
docker compose run --rm pipeline python src/consultar.py "SELECT table_schema,table_name,table_type FROM information_schema.tables WHERE table_schema IN ('silver','gold') ORDER BY 1,2"
```

Solo deben aparecer `silver.movimientos`, `silver.cuarentena` y `gold.movimientos`, todas `BASE TABLE`.

Conteos y fechas:

```powershell
docker compose run --rm pipeline python src/consultar.py "SELECT estado,fecha_corte,count(*) cantidad FROM silver.movimientos GROUP BY estado,fecha_corte ORDER BY estado"
docker compose run --rm pipeline python src/consultar.py "SELECT fecha_corte,count(*) cantidad FROM silver.cuarentena GROUP BY fecha_corte"
docker compose run --rm pipeline python src/consultar.py "SELECT fecha_corte,count(*) cantidad FROM gold.movimientos GROUP BY fecha_corte"
```

| Tabla/estado | fecha_corte | Cantidad |
|---|---|---:|
| silver.movimientos / nuevo | 2026-09-25 | 13.199 |
| silver.movimientos / eliminado | 2026-09-25 | 14.051 |
| silver.movimientos / sin_cambios | 2026-09-25 | 33.372 |
| silver.cuarentena | 2026-09-25 | 2.429 |
| gold.movimientos | 2026-09-25 | 46.571 |

`corregido` no tiene filas con la llave de todos los campos. Los eliminados llevan la fecha del corte en que se detectó su ausencia. La fecha de proceso será la de tu ejecución, no necesariamente la fecha de corte.

## 5. Localizar los archivos generados

En Windows, dentro del proyecto:

```text
data/output/movimientos.duckdb
data/output/bronze/T.parquet
data/output/bronze/T1.parquet
```

El volumen de Compose hace que los resultados permanezcan después de terminar el contenedor. No abrir `movimientos.duckdb` como texto; consultar con los comandos anteriores. Cerrar conexiones de otras aplicaciones si se produce un bloqueo del archivo durante la escritura.

## 6. Ejecutar nuevamente

```powershell
docker compose up --build
```

Si ya se procesaron los mismos archivos con las mismas fechas, se informa que están cargados y no se duplican registros. Para terminar los recursos de Compose cuando ya no se necesiten:

```powershell
docker compose down
```

Esto no borra los archivos de `data/output`, porque están en una carpeta montada desde Windows.

## 7. Problemas habituales

| Mensaje o situación | Acción |
|---|---|
| `docker` no se reconoce | Instalar Docker Desktop; cerrar y abrir la terminal para actualizar PATH. |
| No se puede conectar al motor | Abrir Docker Desktop y esperar a que inicie el motor Linux. |
| WSL requiere actualización | Seguir las indicaciones de Docker Desktop y reiniciar si lo pide. |
| No se encuentra archivo Compose | Abrir la terminal en la carpeta que contiene `docker-compose.yml`. |
| No se encuentra un Parquet | Revisar nombres y ubicación dentro de `data/raw`. |
| El corte ya existe con otra fecha | Se está usando una base anterior. Descomprimir esta entrega en una carpeta nueva y ejecutar allí. |
| Base de versión anterior | No mezclar esta versión con la base de modelos anteriores; reconstruir desde sus archivos en otra carpeta. |
| El contenedor termina con código 0 | Es el resultado esperado de una carga batch completada. |

Verificación realizada al preparar esta entrega: pruebas nativas y carga de ambos Parquet con las fechas indicadas. Docker no está instalado en el entorno de preparación, por lo que aquí no se ejecutó la construcción ni el contenedor.
