"""Cortes completos: dos tablas silver y una tabla gold."""
import argparse
import hashlib
import logging
import re
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
COLUMNS = 'id_cliente,date,product,type,fund,amount,description,commercial_name'
EXPECTED = set(COLUMNS.split(','))
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def normalize(con, path):
    """Lee con DuckDB y prepara raw/limpio temporales sin cargar filas en Python."""
    con.read_parquet(str(path)).create_view('_archivo', replace=True)
    columns = {row[0] for row in con.sql('DESCRIBE _archivo').fetchall()}
    if columns != EXPECTED:
        raise ValueError('Esquema inesperado. Se requieren exactamente: ' + COLUMNS)
    con.execute('CREATE OR REPLACE TEMP TABLE raw AS SELECT row_number() OVER () fila_origen, * FROM _archivo')
    con.execute('DROP VIEW _archivo')
    rows = con.sql('SELECT count(*) FROM raw').fetchone()[0]
    if rows == 0:
        raise ValueError('Corte vacío: revisar completitud antes de publicar.')
    con.execute((SRC / 'normalizar.sql').read_text(encoding='utf-8'))
    return rows


def process_cut(source, output, label, order, cut_date=None):
    """Publica el último corte; fecha desconocida = NULL, nunca una fecha inventada."""
    source, output = Path(source), Path(output)
    if not re.fullmatch(r'[A-Za-z0-9_-]+', label) or order < 1:
        raise ValueError('Corte inválido u orden no positivo.')
    if isinstance(cut_date, str):
        cut_date = date.fromisoformat(cut_date)
    output.mkdir(parents=True, exist_ok=True)
    bronze = output / 'bronze' / f'{label}.parquet'
    bronze.parent.mkdir(exist_ok=True)
    checksum = sha256(source)
    with duckdb.connect(str(output / 'movimientos.duckdb')) as con:
        con.execute("SET memory_limit='512MB'; SET threads=2; SET TimeZone='UTC'")
        con.execute('SET temp_directory=?', [str(output / 'tmp')])
        # Evita mezclar esta versión con el modelo antiguo de tablas/vistas.
        legacy = con.sql("SELECT count(*) FROM information_schema.tables WHERE table_schema='silver' AND table_name='comparacion'").fetchone()[0]
        if legacy:
            raise ValueError('Base de versión anterior. Usar una carpeta --output nueva para reconstruir.')
        con.execute('CREATE SCHEMA IF NOT EXISTS bronze; CREATE SCHEMA IF NOT EXISTS silver; CREATE SCHEMA IF NOT EXISTS gold')
        con.execute('''CREATE TABLE IF NOT EXISTS bronze.cargas(
            corte VARCHAR PRIMARY KEY, orden INTEGER UNIQUE, fecha_corte DATE,
            archivo VARCHAR, sha256 VARCHAR, filas BIGINT, fecha_proceso TIMESTAMP)''')
        existing = con.execute('SELECT orden,sha256,fecha_corte FROM bronze.cargas WHERE corte=?',[label]).fetchone()
        if existing:
            if existing != (order,checksum,cut_date):
                raise ValueError('El corte ya existe con otro contenido, fecha u orden.')
            if not bronze.exists() or sha256(bronze) != checksum:
                raise ValueError('La copia bronze no coincide con el manifiesto.')
            logging.info('%s ya cargado; se conservan los resultados del último corte.',label)
            return
        previous = con.sql('SELECT corte,orden,archivo,sha256 FROM bronze.cargas ORDER BY orden DESC LIMIT 1').fetchone()
        if previous and order <= previous[1]:
            raise ValueError('Los cortes nuevos deben llegar en orden creciente.')
        last_date = con.sql('SELECT max(fecha_corte) FROM bronze.cargas').fetchone()[0]
        if cut_date and last_date and cut_date <= last_date:
            raise ValueError('La fecha del nuevo corte debe ser posterior a las fechas conocidas.')
        if bronze.exists():
            if sha256(bronze) != checksum:
                raise ValueError('Ya existe otro archivo bronze con esa etiqueta.')
            candidate = bronze
        else:
            candidate = bronze.with_suffix('.tmp')
            shutil.copyfile(source,candidate)
            if sha256(candidate) != checksum:
                raise ValueError('El archivo cambió durante la copia.')
        rows = normalize(con,candidate)
        con.execute(f"CREATE TEMP TABLE actual AS SELECT {COLUMNS} FROM limpio WHERE motivos=''")
        # Conserva los valores crudos de los rechazos, incluso fechas no convertibles.
        con.execute('''CREATE TEMP TABLE rechazados AS SELECT r.* EXCLUDE(fila_origen), l.motivos
            FROM raw r JOIN limpio l USING(fila_origen) WHERE l.motivos<>'' ''')
        if candidate != bronze:
            candidate.replace(bronze)
        if previous:
            previous_path = output / previous[2]
            if sha256(previous_path) != previous[3]:
                raise ValueError('El bronze del corte anterior fue modificado.')
            normalize(con,previous_path)
            con.execute(f"CREATE TEMP TABLE anterior AS SELECT {COLUMNS} FROM limpio WHERE motivos=''")
        else:
            con.execute('CREATE TEMP TABLE anterior AS SELECT * FROM actual WHERE false')
        processed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        con.execute('CREATE TEMP TABLE contexto AS SELECT ?::DATE fecha_corte, ?::TIMESTAMP fecha_proceso',[cut_date,processed_at])
        con.execute('BEGIN TRANSACTION')
        try:
            con.execute((SRC / 'silver.sql').read_text(encoding='utf-8'))
            con.execute((SRC / 'gold.sql').read_text(encoding='utf-8'))
            valid = con.sql('SELECT count(*) FROM gold.movimientos').fetchone()[0]
            rejected = con.sql('SELECT count(*) FROM silver.cuarentena').fetchone()[0]
            if valid + rejected != rows:
                raise ValueError('No se cumple: filas recibidas = vigentes válidas + cuarentena.')
            con.execute('INSERT INTO bronze.cargas VALUES (?,?,?,?,?,?,?)',
                        [label,order,cut_date,f'bronze/{label}.parquet',checksum,rows,processed_at])
            con.execute('COMMIT')
        except Exception:
            con.execute('ROLLBACK')
            raise
        logging.info('%s: recibidas=%s, vigentes válidas=%s, cuarentena=%s',label,rows,valid,rejected)
        logging.info('Estados silver: %s',con.sql('SELECT estado,count(*) FROM silver.movimientos GROUP BY estado').fetchall())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archivo',type=Path)
    parser.add_argument('--corte')
    parser.add_argument('--orden',type=int)
    parser.add_argument('--fecha-corte',type=date.fromisoformat)
    parser.add_argument('--completo',action='store_true')
    parser.add_argument('--fecha-t',type=date.fromisoformat)
    parser.add_argument('--fecha-t1',type=date.fromisoformat)
    parser.add_argument('--output',type=Path,default=ROOT / 'data/output')
    args = parser.parse_args()
    if args.archivo:
        if not args.corte or args.orden is None or not args.fecha_corte or not args.completo:
            parser.error('Corte nuevo: --archivo --corte --orden --fecha-corte YYYY-MM-DD --completo')
        if args.fecha_t or args.fecha_t1:
            parser.error('--fecha-t/--fecha-t1 corresponden solo a los archivos del ejemplo.')
        cuts = [(args.archivo,args.corte,args.orden,args.fecha_corte)]
    else:
        if args.corte or args.orden is not None or args.fecha_corte or args.completo:
            parser.error('Falta --archivo')
        if bool(args.fecha_t) != bool(args.fecha_t1):
            parser.error('Proporcionar ambas fechas: --fecha-t y --fecha-t1')
        fecha_t = args.fecha_t or date(2026,9,24)
        fecha_t1 = args.fecha_t1 or date(2026,9,25)
        if fecha_t1 <= fecha_t:
            parser.error('La fecha T1 debe ser posterior a T')
        cuts = [(ROOT / 'data/raw/movimientos_dia_T.parquet','T',1,fecha_t),
                (ROOT / 'data/raw/movimientos_dia_T1.parquet','T1',2,fecha_t1)]
    for source,label,order,cut_date in cuts:
        process_cut(source,args.output,label,order,cut_date)


if __name__ == '__main__':
    main()
