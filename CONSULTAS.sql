-- Inventario: deben aparecer 2 tablas silver y 1 gold, ninguna vista.
SELECT table_schema, table_name, table_type
FROM information_schema.tables
WHERE table_schema IN ('silver','gold')
ORDER BY table_schema, table_name;

-- Cuatro estados, incluidos aquellos sin registros.
SELECT e.estado, count(m.estado) AS cantidad
FROM (VALUES ('nuevo'),('eliminado'),('sin_cambios'),('corregido')) e(estado)
LEFT JOIN silver.movimientos m ON m.estado = e.estado
GROUP BY e.estado ORDER BY e.estado;

-- Cantidades de las tres tablas.
SELECT 'silver.movimientos' AS tabla, count(*) AS filas FROM silver.movimientos
UNION ALL SELECT 'silver.cuarentena', count(*) FROM silver.cuarentena
UNION ALL SELECT 'gold.movimientos', count(*) FROM gold.movimientos;

-- Rechazos y motivo (una fila puede tener varios motivos concatenados).
SELECT motivos, count(*) AS cantidad
FROM silver.cuarentena GROUP BY motivos ORDER BY cantidad DESC;

-- Últimos metadatos y etiquetas originales están en bronze.
SELECT * FROM bronze.cargas ORDER BY orden;

-- Inspección de los registros y de las fechas.
SELECT * FROM silver.movimientos LIMIT 20;
SELECT * FROM silver.cuarentena LIMIT 20;
SELECT * FROM gold.movimientos LIMIT 20;

-- Actividad por producto. Importes comparables solo si comparten moneda/unidad.
SELECT product, count(*) AS movimientos,
    sum(CASE WHEN type='entrada' THEN amount ELSE 0 END) AS entradas,
    sum(CASE WHEN type='salida' THEN amount ELSE 0 END) AS salidas
FROM gold.movimientos GROUP BY product ORDER BY product;
