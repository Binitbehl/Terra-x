# src/process/export_stations.py
import duckdb
duckdb.connect("data/processed/terra.duckdb", read_only=True).execute(
    "COPY stations TO 'data/processed/stations.csv' (HEADER, DELIMITER ',')")
print("saved data/processed/stations.csv")