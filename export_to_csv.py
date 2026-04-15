
import sqlite3
import pandas as pd
import os

import sqlite3
import pandas as pd
import os
import sys
import glob

def get_latest_db():
    # Find all generated DBs in the output folder
    search_path = os.path.join('output', '**', 'generated_*.db')
    dbs = glob.glob(search_path, recursive=True)
    if not dbs:
        # Fallback to older consulting.db
        if os.path.exists('output/consulting.db'): return 'output/consulting.db'
        print("No database found.")
        sys.exit(1)
    # Return the most recently modified database
    return max(dbs, key=os.path.getmtime)

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else get_latest_db()

# Create an output directory matching the DB name next to the DB
db_name = os.path.splitext(os.path.basename(DB_PATH))[0]
OUTPUT_DIR = os.path.join(os.path.dirname(DB_PATH), db_name)

os.makedirs(OUTPUT_DIR, exist_ok=True)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Get all user tables (skip sqlite internal tables)
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
tables = [row[0] for row in cursor.fetchall()]

print("="*60)
print(f"Exporting {len(tables)} tables from {DB_PATH}")
print(f"To directory: {OUTPUT_DIR}/")
print("="*60)

for table in tables:
    df = pd.read_sql_query(f"SELECT * FROM [{table}]", conn)
    csv_path = os.path.join(OUTPUT_DIR, f"{table}.csv")
    df.to_csv(csv_path, index=False)
    print(f"  ✓ Exported {table:32}  ({len(df):>7} rows)")

conn.close()
print("\nExport complete!")
