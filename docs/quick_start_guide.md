# Quick Start: Running the Consulting Firm Simulation

## Prerequisites
- Python 3.10+
- Node.js 18+

## Setup (one-time)
```bash
git clone https://github.com/AIdoAI/RelSim.git
cd RelSim

# Python deps
pip install -r python/requirements.txt

# UI deps
cd electron && npm install && cd ..
```

## Option A: Run via CLI
```bash
cd python

# 1. Generate database + run simulation
python3 main.py simulate consulting_sim.yaml consulting_db.yaml -o output -n consulting

# 2. Run post-processing scripts (populates Consultant_Title_History & Deliverable_Progress_Month)
python3 generate_title_history.py
python3 generate_progress_months.py
```
Output: `output/consulting.db` (SQLite database with all 13 tables populated)

## Option B: Run via Electron App
```bash
cd electron
unset ELECTRON_RUN_AS_NODE && npm run dev
```
1. Open the **Consulting Firm** project in the sidebar
2. Click **Generate** → creates the database
3. Click **Run Simulation** → runs the simulation
4. Go to **Results** tab → browse tables and export CSV

## Export CSVs (after CLI run)
```bash
cd python
python3 -c "
import sqlite3, csv, os
os.makedirs('../output/csv', exist_ok=True)
conn = sqlite3.connect('../output/consulting.db')
for table in [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'\").fetchall()]:
    rows = conn.execute(f'SELECT * FROM \"{table}\"').fetchall()
    cols = [d[0] for d in conn.execute(f'SELECT * FROM \"{table}\" LIMIT 0').description]
    with open(f'../output/csv/{table}.csv','w',newline='') as f:
        w = csv.writer(f); w.writerow(cols); w.writerows(rows)
    print(f'{table}: {len(rows)} rows')
conn.close()
"
```

## YAML Files
| File | Purpose |
|------|---------|
| `python/consulting_db.yaml` | Database schema — 13 tables, columns, generators |
| `python/consulting_sim.yaml` | Simulation config — 10-year run, resources, 5-deliverable workflow |

## Expected Output (13 tables)
| Table | ~Rows | Description |
|-------|-------|-------------|
| Location | 30 | Office locations |
| Client | 20 | Client companies |
| BusinessUnit | 5 | Consulting divisions |
| Title | 6 | Consultant title levels |
| Consultant | 60 | Consultant profiles |
| Consultant_Title_History | 99 | Promotion history |
| Project | ~113 | Client projects (~98% Complete) |
| ProjectBillingRate | ~678 | Billing rates per project/title |
| Deliverable | ~444 | Project deliverables |
| ProjectExpense | ~554 | Project expenses |
| Deliverable_Title_Plan_Mapping | ~2664 | Planned hours per title |
| Consultant_Deliverable_Mapping | ~1322 | Consultant assignments |
| Deliverable_Progress_Month | ~516 | Monthly progress tracking |

> **Note on macOS:** Port 5000 is used by AirPlay Receiver. The app uses port 5001 instead. If port 5001 is busy, kill it with `lsof -ti:5001 | xargs kill`.
