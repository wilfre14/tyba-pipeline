CREATE OR REPLACE TEMP TABLE limpio AS
WITH normalizado AS (
    SELECT fila_origen,
        nullif(trim(id_cliente), '') AS id_cliente,
        coalesce(try_strptime(date, '%Y-%m-%d'),
                 try_strptime(date, '%d/%m/%Y'))::DATE AS date,
        nullif(lower(trim(product)), '') AS product,
        CASE lower(trim(type))
            WHEN 'in' THEN 'entrada' WHEN 'entrada' THEN 'entrada'
            WHEN 'out' THEN 'salida' WHEN 'salida' THEN 'salida'
            ELSE nullif(lower(trim(type)), '') END AS type,
        nullif(lower(trim(fund)), '') AS fund,
        try_cast(amount AS DECIMAL(20,2)) AS amount,
        try_cast(amount AS DOUBLE) < 0 AS monto_negativo,
        nullif(trim(description), '') AS description,
        nullif(trim(commercial_name), '') AS commercial_name
    FROM raw
)
SELECT * EXCLUDE (monto_negativo), concat_ws('|',
    CASE WHEN id_cliente IS NULL THEN 'cliente_vacio' END,
    CASE WHEN date IS NULL THEN 'fecha_invalida' END,
    CASE WHEN product IS NULL THEN 'producto_vacio' END,
    CASE WHEN fund IS NULL THEN 'fondo_vacio' END,
    CASE WHEN type IS NULL OR type NOT IN ('entrada','salida') THEN 'tipo_invalido' END,
    CASE WHEN amount IS NULL THEN 'monto_nulo_o_invalido' END,
    CASE WHEN monto_negativo THEN 'monto_negativo_revisar' END
) AS motivos
FROM normalizado;
