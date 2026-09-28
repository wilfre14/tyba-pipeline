-- Solo dos tablas persistentes. Las tablas auxiliares son TEMP y desaparecen.
-- Comparamos los ocho campos normalizados; ALL conserva las repeticiones.
-- Cambiar un campo cambia la llave: eliminado + nuevo. Corregido no es detectable.
CREATE OR REPLACE TABLE silver.movimientos AS
SELECT d.*, c.fecha_corte, c.fecha_proceso
FROM (
    SELECT a.*, 'nuevo' AS estado FROM (
        SELECT * FROM actual EXCEPT ALL SELECT * FROM anterior
    ) a
    UNION ALL
    SELECT a.*, 'eliminado' AS estado FROM (
        SELECT * FROM anterior EXCEPT ALL SELECT * FROM actual
    ) a
    UNION ALL
    SELECT a.*, 'sin_cambios' AS estado FROM (
        SELECT * FROM actual INTERSECT ALL SELECT * FROM anterior
    ) a
) d CROSS JOIN contexto c;

-- Rechazos del corte actual, con valores originales y motivos de calidad.
CREATE OR REPLACE TABLE silver.cuarentena AS
SELECT r.*, c.fecha_corte, c.fecha_proceso
FROM rechazados r CROSS JOIN contexto c;
