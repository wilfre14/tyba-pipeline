import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.output = self.root / 'output'

    def tearDown(self):
        self.temp.cleanup()

    def row(self, amount=10, day='2024-01-01', kind='entrada', description=None):
        return ('C1', day, ' ETF ', kind, ' Renta Fija ', amount, description, None)

    def source(self, name, rows):
        path = self.root / name
        with duckdb.connect() as con:
            con.execute('''CREATE TABLE r(id_cliente VARCHAR,date VARCHAR,product VARCHAR,
                type VARCHAR,fund VARCHAR,amount DOUBLE,description VARCHAR,commercial_name VARCHAR)''')
            if rows:
                con.executemany('INSERT INTO r VALUES (?,?,?,?,?,?,?,?)', rows)
            con.execute('COPY r TO ? (FORMAT PARQUET)', [str(path)])
        return path

    def run_cut(self, path, label='T', order=1, cut_date=None):
        self.assertTrue((ROOT / 'src/pipeline.py').exists(), 'Falta implementar pipeline')
        from pipeline import process_cut
        process_cut(path, self.output, label, order, cut_date)

    def query(self, sql):
        with duckdb.connect(str(self.output / 'movimientos.duckdb'), read_only=True) as con:
            return con.sql(sql).fetchall()

    def test_exact_tables_and_columns(self):
        self.run_cut(self.source('a.parquet', [self.row()]))
        self.assertEqual(self.query("SELECT table_schema,table_name,table_type FROM information_schema.tables WHERE table_schema IN ('silver','gold') ORDER BY 1,2"),
                         [('gold','movimientos','BASE TABLE'),('silver','cuarentena','BASE TABLE'),('silver','movimientos','BASE TABLE')])
        columns = [r[0] for r in self.query('DESCRIBE silver.movimientos')]
        self.assertEqual(columns, ['id_cliente','date','product','type','fund','amount','description','commercial_name','estado','fecha_corte','fecha_proceso'])

    def test_quarantine_is_physical_and_preserves_raw_errors(self):
        self.run_cut(self.source('a.parquet', [self.row(), self.row(-1), self.row(None), self.row(3, 'bad'), self.row(0)]))
        self.assertEqual(self.query('SELECT count(*) FROM silver.movimientos'), [(2,)])
        self.assertEqual(self.query('SELECT count(*) FROM gold.movimientos'), [(2,)])
        self.assertEqual(self.query('SELECT count(*) FROM silver.cuarentena'), [(3,)])
        self.assertEqual(self.query("SELECT date FROM silver.cuarentena WHERE motivos LIKE '%fecha_invalida%'"), [('bad',)])

    def test_negative_amount_cannot_be_hidden_by_rounding(self):
        self.run_cut(self.source('a.parquet',[self.row(-0.001),self.row(1)]))
        self.assertEqual(self.query('SELECT count(*) FROM gold.movimientos'),[(1,)])
        self.assertEqual(self.query('SELECT amount,motivos FROM silver.cuarentena'),[(-0.001,'monto_negativo_revisar')])

    def test_states_duplicates_and_gold_current(self):
        self.run_cut(self.source('a.parquet', [self.row(),self.row(),self.row(20)]), cut_date=date(2024,1,2))
        self.run_cut(self.source('b.parquet', [self.row(),self.row(25)]),'T1',2,date(2024,1,3))
        self.assertEqual(dict(self.query('SELECT estado,count(*) FROM silver.movimientos GROUP BY estado')),
                         {'nuevo':1,'eliminado':2,'sin_cambios':1})
        self.assertEqual(self.query('SELECT amount FROM gold.movimientos ORDER BY amount'), [(10,),(25,)])
        self.assertEqual(self.query('SELECT DISTINCT fecha_corte FROM silver.movimientos'), [(date(2024,1,3),)])
        self.assertEqual(self.query('SELECT count(DISTINCT fecha_proceso) FROM silver.movimientos'), [(1,)])

    def test_rerun_old_cut_does_not_republish_old_gold(self):
        a = self.source('a.parquet', [self.row()])
        b = self.source('b.parquet', [self.row(25)])
        self.run_cut(a)
        self.run_cut(b,'T1',2)
        before = self.query('SELECT * FROM gold.movimientos')
        self.run_cut(a)
        self.run_cut(b,'T1',2)
        self.assertEqual(before,self.query('SELECT * FROM gold.movimientos'))
        self.assertEqual(self.query('SELECT count(*) FROM bronze.cargas'), [(2,)])

    def test_empty_can_be_corrected_and_invalid_type_is_rejected(self):
        with self.assertRaises(ValueError):
            self.run_cut(self.source('empty.parquet', []))
        self.run_cut(self.source('valid.parquet', [self.row(kind='otro')]))
        self.assertEqual(self.query('SELECT count(*) FROM gold.movimientos'), [(0,)])
        self.assertEqual(self.query('SELECT count(*) FROM silver.cuarentena'), [(1,)])

    def test_changed_cut_order_date_and_schema_are_rejected(self):
        a = self.source('a.parquet',[self.row()])
        b = self.source('b.parquet',[self.row(5)])
        self.run_cut(a,cut_date=date(2024,1,2))
        for path,label,order,day in [(b,'T',1,date(2024,1,2)),(a,'T',1,date(2024,1,3)),
                                      (b,'T1',1,date(2024,1,3)),(b,'T1',2,date(2024,1,1))]:
            with self.assertRaises(ValueError):
                self.run_cut(path,label,order,day)
        bad = self.root / 'bad.parquet'
        with duckdb.connect() as con:
            con.execute('COPY (SELECT 1 x) TO ? (FORMAT PARQUET)',[str(bad)])
        with self.assertRaises(ValueError):
            self.run_cut(bad,'T1',2,date(2024,1,3))
        self.assertEqual(self.query('SELECT amount FROM gold.movimientos'),[(10,)])

    def test_format_changes_match_and_unknown_cut_date_is_null(self):
        self.run_cut(self.source('a.parquet',[self.row()]))
        self.run_cut(self.source('b.parquet',[self.row(day='01/01/2024',kind='IN')]),'T1',2)
        self.assertEqual(self.query('SELECT estado,fecha_corte FROM silver.movimientos'),[('sin_cambios',None)])

    def test_deleted_rows_are_not_carried_to_later_comparisons(self):
        self.run_cut(self.source('a.parquet',[self.row(),self.row(20)]))
        self.run_cut(self.source('b.parquet',[self.row()]),'T1',2)
        self.run_cut(self.source('c.parquet',[self.row()]),'T2',3,date(2024,1,4))
        self.assertEqual(self.query('SELECT estado,amount FROM silver.movimientos'),[('sin_cambios',10)])


if __name__ == '__main__':
    unittest.main()
