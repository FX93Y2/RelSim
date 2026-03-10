# Consulting Firm Database — PPTX v2 Implementation Report

**Reference:** `Consulting_Firm_Synthetic_Database_Generation-1.pptx` (19 slides)  
**Repository:** https://github.com/AIdoAI/RelSim  
**Branch:** `pptx-v2-schema-updates` (merged into `main`)  
**Date:** March 10, 2026

---

## 1. Database Schema (consulting_db.yaml)

### 1.1 Table Names — Aligned to Slide 8 Data Model

All 13 tables use consistent underscore naming matching the PPTX specification:

| # | Table Name | Type | Rows | Notes |
|---|-----------|------|------|-------|
| 1 | `Region` | entity | 30 | Renamed from `Location` per Slide 7/8 |
| 2 | `Client` | entity | 20 | ClientIDs start at 1000 (4-digit) |
| 3 | `Business_Unit` | entity | 5 | Deterministic IDs 1001–1005 |
| 4 | `Title` | entity | 6 | Deterministic IDs 101–106, column renamed from `TitleName` to `Title` |
| 5 | `Consultant` | resource | 60 | Simplified to `ConsultantName` (was FirstName + LastName) |
| 6 | `Consultant_Title_History` | bridge | ~99 | Populated by `generate_title_history.py` |
| 7 | `Project_Plan` | entity | ~120 | Renamed from `Project` per Slide 8 |
| 8 | `Project_Billing_Rate` | bridge | ~720 | 6 per project (one per title) |
| 9 | `Deliverable` | entity | ~500 | 5 per project (lifecycle phases) |
| 10 | `Deliverable_Title_Plan_Mapping` | bridge | ~3000 | 6 per deliverable (one per title) |
| 11 | `Consultant_Deliverable_Mapping` | bridge | ~1500 | Column renamed from `Hours` to `ActualHours` |
| 12 | `Actual_Project_Expense` | entity | ~580 | Renamed from `ProjectExpense`, FK is `DeliverableID` (not ProjectID) |
| 13 | `Deliverable_Progress_Month` | bridge | varies | Populated by `generate_progress_months.py` |

### 1.2 Key Schema Changes from v1

| Change | Old (v1) | New (v2) | Spec Ref |
|--------|---------|---------|----------|
| Region table | `Location` | `Region` | Slide 7/8 |
| Project table | `Project` | `Project_Plan` | Slide 8 |
| Expense table | `ProjectExpense` (FK: ProjectID) | `Actual_Project_Expense` (FK: DeliverableID) | Slide 7/10 |
| Business Unit | `BusinessUnit` | `Business_Unit` | Slide 8 |
| Billing Rate | `ProjectBillingRate` | `Project_Billing_Rate` | Slide 8 |
| BU IDs | Auto-increment | 1001–1005 (deterministic) | Slide 8 |
| Title IDs | Auto-increment | 101–106 (deterministic) | Slide 8 |
| Client IDs | Auto-increment | 1000+ (4-digit) | Slide 8 |
| Title column | `TitleName` | `Title` | Slide 8 |
| Consultant | `FirstName`, `LastName`, `Email`, `Phone` | `ConsultantName` | Slide 8 |
| CDM hours | `Hours` | `ActualHours` | Slide 10 |
| Deliverable | — | Added `DeliverableFixedPrice` | Slide 10 |
| Project | — | Added `EstimatedBudget`, `PlannedHours` | Slide 10 |

### 1.3 Deterministic Values

**Business Units (IDs 1001–1005):** Retail, Healthcare, Media & Entertainment, Energy, Government

**Titles (IDs 101–106):** Consultant, Senior Consultant, Manager, Senior Manager, Associate Partner, Partner

---

## 2. Simulation Flow (consulting_sim.yaml)

### 2.1 Project Lifecycle

Each project follows a 5-deliverable workflow (Slide 14–15):

```
Create Project → Trigger Billing Rates → Set Status "In Progress"
  → Create Deliverable 1 (Project Plan Development)
    → Process D1 (~4 weeks) → Create D2 (Design)
      → Process D2 (~3 weeks) → Create D3 (Infrastructure)
        → Process D3 (~5 weeks) → Create D4 (Coding & Unit Test)
          → Process D4 (~6 weeks) → Create D5 (System Test)
            → Process D5 (~2 weeks) → Trigger Expenses → Set Status "Complete"
```

### 2.2 Key Parameters

- **Simulation Duration:** 1825 days (5 years)
- **Project Interarrival:** EXPO(30) days (~1 per month)
- **Project Type:** 50% Fixed-Price / 50% Time & Materials
- **Fixed Price Amount:** UNIF(50000, 500000)
- **Resources:** 60 consultants, 2–3 assigned per deliverable

---

## 3. Post-Processing Scripts

| Script | Purpose |
|--------|---------|
| `generate_title_history.py` | Assigns 1–3 title promotions per consultant with realistic salary ranges |
| `fix_billing_rates.py` | Assigns TitleIDs to billing rates and applies title-specific rate distributions (Consultant ~$150/hr, Partner ~$500/hr) |
| `calculate_financials.py` | Populates `PlannedHours` and `EstimatedBudget` on `Project_Plan` from deliverable data |
| `generate_progress_months.py` | Creates monthly progress tracking rows for `Deliverable_Progress_Month` |
| `generate_reports.py` | Generates 13 management reports (see Section 4) |

---

## 4. Management Reports (generate_reports.py)

### Per Consultant
| # | Report | Output File |
|---|--------|-------------|
| 1 | Projects worked on YTD + hours per project | `report_01_consultant_projects.csv` |

### Per Business Unit
| # | Report | Output File |
|---|--------|-------------|
| 2 | Total revenue (current month & YTD) | `report_02_bu_revenue.csv` |
| 3 | Forecasted revenue for remainder of year | `report_03_bu_forecasted_revenue.csv` |
| 4 | Forecasted profit at end of year | `report_04_bu_forecasted_profit.csv` |

### Per Project
| # | Report | Output File |
|---|--------|-------------|
| 5 | Overall percentage complete | `report_05_project_pct_complete.csv` |
| 6 | Hours expended & expenses to date | `report_06_project_hours_expenses.csv` |
| 7 | Forecasted hours to complete | `report_07_forecasted_hours.csv` |
| 8 | Planned hours to complete (by title) | `report_08_planned_hours.csv` |

### Per Fixed-Price Project
| # | Report | Output File |
|---|--------|-------------|
| 9 | Contract value | Combined in `report_09_13_fixed_price.csv` |
| 10 | Revenue to date | |
| 11 | Costs to date (payroll + expenses) | |
| 12 | Expected costs at completion | |
| 13 | Expected profit | |

---

## 5. Engine Enhancements

| Enhancement | File | Description |
|------------|------|-------------|
| `id_offset` generator | `db_parser.py`, `attribute_generator.py` | Allows PKs to start at custom offsets (e.g., 1000 for clients) |
| `ordered_list` generator | `attribute_generator.py` | Assigns values in order from a fixed list (e.g., BU names) |
| Bridge table PK relaxation | `db_parser.py` | Bridge tables no longer require explicit PKs |
| Synthetic `_rowid` PK | `table_builder.py` | Auto-adds `_rowid` for PK-less bridge tables |
| Conditional column insert | `event_tracker.py` | Handles schema changes gracefully for bridge tables |

---

## 6. Files Changed

### New Files
- `python/generate_reports.py` — 13 management reports
- `python/calculate_financials.py` — Project financial calculations
- `python/fix_billing_rates.py` — Title-specific billing rate assignment
- `python/generate_progress_months.py` — Monthly progress data
- `docs/quick_start_guide.md` — Quick start guide

### Modified Files — Schema & Config
- `python/consulting_db.yaml` — All table/column renames per Slide 8
- `python/consulting_sim.yaml` — Updated entity_table and trigger references

### Modified Files — Engine
- `python/src/config_parser/db_parser.py` — `id_offset` + `subtype` parameters
- `python/src/generator/data/attribute_generator.py` — `ordered_list` generator
- `python/src/generator/schema/table_builder.py` — Synthetic `_rowid` for bridge tables
- `python/src/simulation/managers/event_tracker.py` — Conditional column insertion
- `python/generate_title_history.py` — TitleID int casting fix

---

## 7. How to Run

### Via Electron App
```bash
cd electron && npm run dev
```
1. Open **Consulting Firm** project → **Generate** → **Simulate**
2. View results in the app or export via scripts

### Via CLI
```bash
cd python

# Generate + Simulate
python3 main.py generate-simulate consulting_db.yaml consulting_sim.yaml -o ../output -n consulting

# Post-processing
CONSULTING_DB_PATH=../output/consulting.db python3 generate_title_history.py
python3 fix_billing_rates.py ../output/consulting.db
python3 calculate_financials.py ../output/consulting.db

# Export CSVs
python3 ../export_to_csv.py ../output/consulting.db ../output/csv

# Generate reports
python3 generate_reports.py ../output/consulting.db ../output/reports
```

---

## 8. Sample Output Summary

| Metric | Value |
|--------|-------|
| Projects | ~120–126 |
| Deliverables | ~480–501 (5 per project) |
| Consultants | 60 |
| Business Units | 5 |
| Billing Rates | ~720–756 (6 per project) |
| Expenses | ~580 |
| Avg Planned Hours/Project | ~1,792 |
| Avg Estimated Budget/Project | ~$566K |
| Billing Rate Range | $83–$600/hr (title-dependent) |
