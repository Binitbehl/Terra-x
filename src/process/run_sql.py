import sys
import duckdb

con = duckdb.connect("data/processed/terra.duckdb", read_only=True)
queries = open(sys.argv[1], encoding="utf-8").read().split(";")
for q in queries:
    if q.strip():
        print("\n" + q.strip().splitlines()[0])   # first line = comment/title
        print(con.execute(q).df().to_string(index=False))