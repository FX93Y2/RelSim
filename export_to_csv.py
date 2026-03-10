
import sqlite3
import pandas as pd
import os

DB_PATH = 'output/consulting.db'
OUTPUT_DIR = 'output/csv'

os.makedirs(OUTPUT_DIR, exist_ok=True)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [row[0] for row in cursor.fetchall()]

print(f"Exporting {len(tables)} tables from {DB_PATH} to {OUTPUT_DIR}...")

for table in tables:
    print(f"  - Exporting {table}...")
    df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    csv_path = os.path.join(OUTPUT_DIR, f"{table}.csv")
    df.to_csv(csv_path, index=False)
    print(f"    -> Saved to {csv_path} ({len(df)} rows)")

conn.close()
print("Export complete!")
