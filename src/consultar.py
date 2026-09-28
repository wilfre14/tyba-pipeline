"""python src/consultar.py 'SELECT ...' [--db ruta.duckdb]"""
import argparse
from pathlib import Path
import duckdb

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('sql',nargs='?',default='SELECT estado,count(*) cantidad FROM silver.movimientos GROUP BY estado')
parser.add_argument('--db',type=Path,default=Path(__file__).resolve().parents[1] / 'data/output/movimientos.duckdb')
args = parser.parse_args()
with duckdb.connect(str(args.db),read_only=True) as con:
    con.sql(args.sql).show(max_rows=40)
