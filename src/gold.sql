-- Única tabla gold: movimientos válidos y vigentes del último corte.
-- Silver ya contiene exclusivamente filas que cumplen las reglas de calidad.
CREATE OR REPLACE TABLE gold.movimientos AS
SELECT * FROM silver.movimientos
WHERE estado IN ('nuevo', 'sin_cambios', 'corregido');
