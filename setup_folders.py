from pathlib import Path

folders = [
    "data/raw", "data/processed",
    "src/ingest", "src/process", "src/features",
    "src/models", "src/eval",
    "notebooks", "sql", "reports",
]
for f in folders:
    p = Path(f)
    p.mkdir(parents=True, exist_ok=True)
    (p / ".gitkeep").touch()
print("Done")