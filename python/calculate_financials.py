"""
Post-processing: Calculate derived financial and date fields.

Project_Plan:
- PlannedStartDate: MIN actual start date across deliverables (from Consultant_Deliverable_Mapping)
- PlannedEndDate:   MAX actual end date across deliverables (from sim_event_processing fallback)
- PlannedHours:     SUM(Deliverable_Title_Plan_Mapping.PlannedHours) per project
- EstimatedBudget:  SUM(PlannedHours * BillingRate) + SUM(PlannedExpense)

Deliverable:
- ActualStartDate:    MIN(Consultant_Deliverable_Mapping.start_date) per deliverable
- ActualEndDate:      MAX(Consultant_Deliverable_Mapping.end_date) per deliverable
- PlannedStartDate:   same as ActualStartDate (best available; set by plan generator when used)
- PlannedEndDate:     same as ActualEndDate
- PlannedExpense:     UNIF(2000, 15000) — planned cost for this deliverable phase
- DeliverableFixedPrice: for Fixed-Price projects only — project Fixed_Price_Amount split
                         proportionally across deliverables using random weights

Actual_Project_Expense:
- Date: copied from created_at (the DES stamps created_at at trigger time)

Usage:
  python calculate_financials.py <path_to_db>
"""

import sys
import sqlite3
import random
from datetime import datetime, timedelta

# Conceptual model: the firm was founded N years before the simulation starts.
# This anchors the static-table created_at dates relative to the simulation.
SIMULATION_START_DATE = "2020-01-01"   # must match consulting_sim.yaml
FIRM_AGE_YEARS = 5                     # years of firm history before simulation begins


def populate_static_created_at(cur) -> None:
    """
    Set created_at on the firm's master/static tables.

    Region, Business_Unit, Title  → all set to the firm founding date
                                    (infrastructure that existed from day 1)
    Client                        → uniform random between founding and
                                    simulation start (each client onboarded
                                    at a different point in firm history)
    """
    sim_start = datetime.strptime(SIMULATION_START_DATE, "%Y-%m-%d")
    firm_founding = sim_start - timedelta(days=365 * FIRM_AGE_YEARS)
    founding_str = firm_founding.strftime("%Y-%m-%d")

    # Infrastructure tables — single founding date
    for tbl in ("Region", "Business_Unit", "Title"):
        cur.execute(
            f"UPDATE {tbl} SET created_at = ? WHERE created_at IS NULL",
            (founding_str,),
        )
        if cur.rowcount > 0:
            print(f"Set {tbl}.created_at = {founding_str} for {cur.rowcount} rows.")

    # Client onboarding — uniform random across the onboarding window
    cur.execute("SELECT ClientID FROM Client WHERE created_at IS NULL")
    client_ids = [row[0] for row in cur.fetchall()]
    if client_ids:
        founding_ts = firm_founding.timestamp()
        sim_start_ts = sim_start.timestamp()
        for cid in client_ids:
            ts = random.uniform(founding_ts, sim_start_ts)
            date_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            cur.execute(
                "UPDATE Client SET created_at = ? WHERE ClientID = ?",
                (date_str, cid),
            )
        print(
            f"Set Client.created_at for {len(client_ids)} rows "
            f"(uniform between {founding_str} and {SIMULATION_START_DATE})."
        )


def calculate_financials(db_path: str) -> None:
    """Calculate derived financial and date fields."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # -------------------------------------------------------------------------
    # STATIC TABLE created_at — Region, Business_Unit, Title, Client
    # Conceptual model: firm founded N years before simulation starts.
    # -------------------------------------------------------------------------
    populate_static_created_at(cur)

    # -------------------------------------------------------------------------
    # PLAN vs ACTUAL DATES (spec slide 3: database must track both)
    #
    # Plan dates come from the DES scheduling (when the entity was created),
    # Actual dates come from Consultant_Deliverable_Mapping (when resources
    # actually started/finished work). The gap between them captures the
    # "onboarding_lag" event on the project side and queue wait on the
    # deliverable side.
    #
    # Project_Plan:
    #   PlannedStartDate = DATE(Project_Plan.created_at)
    #     = the moment the project "enters the system" in SimPy (spec slide 24
    #       "a new project enters the system following EXPO distribution")
    #   ActualStartDate  = MIN(cdm.start_date) across the project's deliverables
    #     = first moment any consultant actually started work
    #   PlannedEndDate   = PlannedStartDate + (ActualEndDate - ActualStartDate)
    #     = the "should have ended by" date if the plan schedule had held
    #   ActualEndDate    = MAX(cdm.end_date) across the project's deliverables
    #
    # Deliverable:
    #   PlannedStartDate = DATE(Deliverable.created_at)
    #     = when the deliverable entity was created by the DES (before
    #       waiting for resources)
    #   ActualStartDate  = MIN(cdm.start_date) for this deliverable
    #     = when resources actually became available and work began
    #   PlannedEndDate   = PlannedStartDate + (ActualEndDate - ActualStartDate)
    #   ActualEndDate    = MAX(cdm.end_date) for this deliverable
    # -------------------------------------------------------------------------

    # ---- Deliverable: Planned dates from created_at ----
    cur.execute("""
        UPDATE Deliverable
        SET PlannedStartDate = DATE(created_at)
        WHERE created_at IS NOT NULL
    """)
    print(f"Updated Deliverable.PlannedStartDate for {cur.rowcount} deliverables.")

    # ---- Deliverable: Actual dates from CDM ----
    cur.execute("""
        UPDATE Deliverable
        SET ActualStartDate = (
            SELECT DATE(MIN(cdm.start_date))
            FROM Consultant_Deliverable_Mapping cdm
            WHERE cdm.DeliverableID = Deliverable.DeliverableID
              AND cdm.start_date IS NOT NULL
        )
        WHERE EXISTS (
            SELECT 1 FROM Consultant_Deliverable_Mapping cdm
            WHERE cdm.DeliverableID = Deliverable.DeliverableID
              AND cdm.start_date IS NOT NULL
        )
    """)
    print(f"Updated Deliverable.ActualStartDate for {cur.rowcount} deliverables.")

    cur.execute("""
        UPDATE Deliverable
        SET ActualEndDate = (
            SELECT DATE(MAX(cdm.end_date))
            FROM Consultant_Deliverable_Mapping cdm
            WHERE cdm.DeliverableID = Deliverable.DeliverableID
              AND cdm.end_date IS NOT NULL
        )
        WHERE EXISTS (
            SELECT 1 FROM Consultant_Deliverable_Mapping cdm
            WHERE cdm.DeliverableID = Deliverable.DeliverableID
              AND cdm.end_date IS NOT NULL
        )
    """)
    print(f"Updated Deliverable.ActualEndDate for {cur.rowcount} deliverables.")

    # ---- Deliverable: PlannedEndDate = PlannedStart + actual duration ----
    # Keeps the variance coming from the DES (duration of NORM(28,7) draws)
    # while anchoring the planned end at the planned-start schedule.
    cur.execute("""
        UPDATE Deliverable
        SET PlannedEndDate = DATE(
            PlannedStartDate,
            '+' || CAST(julianday(ActualEndDate) - julianday(ActualStartDate) AS INTEGER) || ' days'
        )
        WHERE PlannedStartDate IS NOT NULL
          AND ActualStartDate  IS NOT NULL
          AND ActualEndDate    IS NOT NULL
    """)
    print(f"Updated Deliverable.PlannedEndDate for {cur.rowcount} deliverables.")

    # ---- Project_Plan: Planned dates from project created_at ----
    cur.execute("""
        UPDATE Project_Plan
        SET PlannedStartDate = DATE(created_at)
        WHERE created_at IS NOT NULL
    """)
    print(f"Updated Project_Plan.PlannedStartDate for {cur.rowcount} projects.")

    # ---- Project_Plan: Actual dates aggregated from deliverable CDM ----
    cur.execute("""
        UPDATE Project_Plan
        SET ActualStartDate = (
            SELECT DATE(MIN(cdm.start_date))
            FROM Deliverable d
            JOIN Consultant_Deliverable_Mapping cdm
                ON cdm.DeliverableID = d.DeliverableID
            WHERE d.ProjectID = Project_Plan.ProjectID
              AND cdm.start_date IS NOT NULL
        )
        WHERE EXISTS (
            SELECT 1
            FROM Deliverable d
            JOIN Consultant_Deliverable_Mapping cdm
                ON cdm.DeliverableID = d.DeliverableID
            WHERE d.ProjectID = Project_Plan.ProjectID
              AND cdm.start_date IS NOT NULL
        )
    """)
    print(f"Updated Project_Plan.ActualStartDate for {cur.rowcount} projects.")

    cur.execute("""
        UPDATE Project_Plan
        SET ActualEndDate = (
            SELECT DATE(MAX(cdm.end_date))
            FROM Deliverable d
            JOIN Consultant_Deliverable_Mapping cdm
                ON cdm.DeliverableID = d.DeliverableID
            WHERE d.ProjectID = Project_Plan.ProjectID
              AND cdm.end_date IS NOT NULL
        )
        WHERE EXISTS (
            SELECT 1
            FROM Deliverable d
            JOIN Consultant_Deliverable_Mapping cdm
                ON cdm.DeliverableID = d.DeliverableID
            WHERE d.ProjectID = Project_Plan.ProjectID
              AND cdm.end_date IS NOT NULL
        )
    """)
    print(f"Updated Project_Plan.ActualEndDate for {cur.rowcount} projects.")

    # ---- Project_Plan: PlannedEndDate = PlannedStart + actual duration ----
    cur.execute("""
        UPDATE Project_Plan
        SET PlannedEndDate = DATE(
            PlannedStartDate,
            '+' || CAST(julianday(ActualEndDate) - julianday(ActualStartDate) AS INTEGER) || ' days'
        )
        WHERE PlannedStartDate IS NOT NULL
          AND ActualStartDate  IS NOT NULL
          AND ActualEndDate    IS NOT NULL
    """)
    print(f"Updated Project_Plan.PlannedEndDate for {cur.rowcount} projects.")

    # -------------------------------------------------------------------------
    # PROJECT_PLAN FINANCIALS
    # -------------------------------------------------------------------------

    cur.execute("""
        UPDATE Project_Plan
        SET PlannedHours = (
            SELECT COALESCE(SUM(dtpm.PlannedHours), 0)
            FROM Deliverable d
            JOIN Deliverable_Title_Plan_Mapping dtpm
                ON d.DeliverableID = dtpm.DeliverableID
            WHERE d.ProjectID = Project_Plan.ProjectID
        )
        WHERE EXISTS (
            SELECT 1 FROM Deliverable d
            JOIN Deliverable_Title_Plan_Mapping dtpm
                ON d.DeliverableID = dtpm.DeliverableID
            WHERE d.ProjectID = Project_Plan.ProjectID
        )
    """)
    print(f"Updated Project_Plan.PlannedHours for {cur.rowcount} projects.")

    # -------------------------------------------------------------------------
    # DELIVERABLE.PlannedExpense — UNIF(2000, 15000) per deliverable
    # Represents the anticipated non-labour cost for each project phase
    # (travel, software, equipment, facilities, etc.).
    # Only fills rows where PlannedExpense is still NULL.
    # -------------------------------------------------------------------------

    cur.execute("SELECT DeliverableID FROM Deliverable WHERE PlannedExpense IS NULL")
    deliverable_ids = [row[0] for row in cur.fetchall()]
    for did in deliverable_ids:
        planned_expense = round(random.uniform(2000, 15000), 2)
        cur.execute("UPDATE Deliverable SET PlannedExpense = ? WHERE DeliverableID = ?",
                    (planned_expense, did))
    print(f"Updated Deliverable.PlannedExpense for {len(deliverable_ids)} deliverables.")

    # -------------------------------------------------------------------------
    # PROJECT_PLAN.PlannedExpense = SUM(Deliverable.PlannedExpense) per project
    # Runs here, after Deliverable.PlannedExpense is populated above.
    # -------------------------------------------------------------------------

    cur.execute("""
        UPDATE Project_Plan
        SET PlannedExpense = (
            SELECT ROUND(SUM(d.PlannedExpense), 2)
            FROM Deliverable d
            WHERE d.ProjectID = Project_Plan.ProjectID
              AND d.PlannedExpense IS NOT NULL
        )
        WHERE EXISTS (
            SELECT 1 FROM Deliverable d
            WHERE d.ProjectID = Project_Plan.ProjectID
              AND d.PlannedExpense IS NOT NULL
        )
    """)
    print(f"Updated Project_Plan.PlannedExpense for {cur.rowcount} projects.")

    # -------------------------------------------------------------------------
    # DELIVERABLE.DeliverableFixedPrice — Fixed-Price projects only
    # Splits the project's Fixed_Price_Amount across its deliverables using
    # random weights so the shares sum exactly to Fixed_Price_Amount.
    # Time & Materials projects leave this column NULL.
    # -------------------------------------------------------------------------

    cur.execute("""
        SELECT p.ProjectID, p.Fixed_Price_Amount
        FROM Project_Plan p
        WHERE p.ProjectType = 'Fixed-Price'
          AND p.Fixed_Price_Amount IS NOT NULL
    """)
    fixed_price_projects = cur.fetchall()
    deliverable_fixed_price_count = 0
    for project_id, fixed_price_amount in fixed_price_projects:
        cur.execute("""
            SELECT DeliverableID FROM Deliverable
            WHERE ProjectID = ? AND DeliverableFixedPrice IS NULL
            ORDER BY DeliverableID
        """, (project_id,))
        delivs = [row[0] for row in cur.fetchall()]
        if not delivs:
            continue
        # Random weights — each deliverable gets a different share
        weights = [random.uniform(0.8, 1.2) for _ in delivs]
        total_weight = sum(weights)
        shares = [round(fixed_price_amount * w / total_weight, 2) for w in weights]
        # Correct rounding drift on the last deliverable
        shares[-1] = round(fixed_price_amount - sum(shares[:-1]), 2)
        for did, share in zip(delivs, shares):
            cur.execute("UPDATE Deliverable SET DeliverableFixedPrice = ? WHERE DeliverableID = ?",
                        (share, did))
        deliverable_fixed_price_count += len(delivs)
    print(f"Updated Deliverable.DeliverableFixedPrice for {deliverable_fixed_price_count} deliverables"
          f" ({len(fixed_price_projects)} Fixed-Price projects).")

    # -------------------------------------------------------------------------
    # CONSULTANT_DELIVERABLE_MAPPING.Month = first day of the month of start_date
    # -------------------------------------------------------------------------

    cur.execute("""
        UPDATE Consultant_Deliverable_Mapping
        SET Month = DATE(start_date, 'start of month')
        WHERE Month IS NULL AND start_date IS NOT NULL
    """)
    print(f"Updated Consultant_Deliverable_Mapping.Month for {cur.rowcount} rows.")

    cur.execute("""
        UPDATE Project_Plan
        SET EstimatedBudget = (
            SELECT COALESCE(labor.total_labor, 0) + COALESCE(expense.total_expense, 0)
            FROM (
                SELECT d.ProjectID,
                       SUM(dtpm.PlannedHours * COALESCE(pbr.BillingRate, 0)) AS total_labor
                FROM Deliverable d
                JOIN Deliverable_Title_Plan_Mapping dtpm
                    ON d.DeliverableID = dtpm.DeliverableID
                LEFT JOIN Project_Billing_Rate pbr
                    ON pbr.ProjectID = d.ProjectID
                   AND pbr.TitleID = dtpm.TitleID
                WHERE d.ProjectID = Project_Plan.ProjectID
                GROUP BY d.ProjectID
            ) labor
            LEFT JOIN (
                SELECT d2.ProjectID,
                       SUM(COALESCE(d2.PlannedExpense, 0)) AS total_expense
                FROM Deliverable d2
                WHERE d2.ProjectID = Project_Plan.ProjectID
                GROUP BY d2.ProjectID
            ) expense ON labor.ProjectID = expense.ProjectID
        )
        WHERE EXISTS (
            SELECT 1 FROM Deliverable d
            WHERE d.ProjectID = Project_Plan.ProjectID
        )
    """)
    print(f"Updated Project_Plan.EstimatedBudget for {cur.rowcount} projects.")

    # -------------------------------------------------------------------------
    # DELIVERABLE_PROGRESS_MONTH.Status — derived from PercentageComplete
    # 'Complete' (=100), 'In Progress' (0<pct<100), 'Not Started' (=0)
    # Adds the column if it doesn't yet exist (older DBs).
    # -------------------------------------------------------------------------

    cur.execute("PRAGMA table_info(Deliverable_Progress_Month)")
    dpm_cols = [row[1] for row in cur.fetchall()]
    if 'Status' not in dpm_cols:
        cur.execute("ALTER TABLE Deliverable_Progress_Month ADD COLUMN Status VARCHAR")
        print("Added Status column to Deliverable_Progress_Month.")

    cur.execute("""
        UPDATE Deliverable_Progress_Month
        SET Status = CASE
            WHEN PercentageComplete >= 100 THEN 'Complete'
            WHEN PercentageComplete > 0    THEN 'In Progress'
            ELSE 'Not Started'
        END
        WHERE Status IS NULL
    """)
    print(f"Updated Deliverable_Progress_Month.Status for {cur.rowcount} rows.")

    # -------------------------------------------------------------------------
    # CONSULTANT_DELIVERABLE_MAPPING — strip time-of-day from start_date/end_date
    # -------------------------------------------------------------------------

    cur.execute("""
        UPDATE Consultant_Deliverable_Mapping
        SET start_date = DATE(start_date)
        WHERE start_date IS NOT NULL AND start_date LIKE '% %'
    """)
    print(f"Stripped time from Consultant_Deliverable_Mapping.start_date for {cur.rowcount} rows.")

    cur.execute("""
        UPDATE Consultant_Deliverable_Mapping
        SET end_date = DATE(end_date)
        WHERE end_date IS NOT NULL AND end_date LIKE '% %'
    """)
    print(f"Stripped time from Consultant_Deliverable_Mapping.end_date for {cur.rowcount} rows.")

    # -------------------------------------------------------------------------
    # SIM_QUEUE_ACTIVITY — strip time-of-day from simulation_datetime
    # -------------------------------------------------------------------------

    cur.execute("""
        UPDATE sim_queue_activity
        SET simulation_datetime = DATE(simulation_datetime)
        WHERE simulation_datetime IS NOT NULL AND simulation_datetime LIKE '% %'
    """)
    print(f"Stripped time from sim_queue_activity.simulation_datetime for {cur.rowcount} rows.")

    # Default priority to 0 for FIFO queue rows where it was left NULL
    cur.execute("""
        UPDATE sim_queue_activity
        SET priority = 0
        WHERE priority IS NULL
    """)
    print(f"Defaulted sim_queue_activity.priority=0 for {cur.rowcount} rows.")

    # -------------------------------------------------------------------------
    # SIM_EVENT_PROCESSING — strip time-of-day from start_datetime/end_datetime
    # -------------------------------------------------------------------------

    cur.execute("""
        UPDATE sim_event_processing
        SET start_datetime = DATE(start_datetime)
        WHERE start_datetime IS NOT NULL AND start_datetime LIKE '% %'
    """)
    print(f"Stripped time from sim_event_processing.start_datetime for {cur.rowcount} rows.")

    cur.execute("""
        UPDATE sim_event_processing
        SET end_datetime = DATE(end_datetime)
        WHERE end_datetime IS NOT NULL AND end_datetime LIKE '% %'
    """)
    print(f"Stripped time from sim_event_processing.end_datetime for {cur.rowcount} rows.")

    # -------------------------------------------------------------------------
    # SIM_RESOURCE_ALLOCATIONS — strip time-of-day from allocation_datetime/release_datetime
    # -------------------------------------------------------------------------

    cur.execute("""
        UPDATE sim_resource_allocations
        SET allocation_datetime = DATE(allocation_datetime)
        WHERE allocation_datetime IS NOT NULL AND allocation_datetime LIKE '% %'
    """)
    print(f"Stripped time from sim_resource_allocations.allocation_datetime for {cur.rowcount} rows.")

    cur.execute("""
        UPDATE sim_resource_allocations
        SET release_datetime = DATE(release_datetime)
        WHERE release_datetime IS NOT NULL AND release_datetime LIKE '% %'
    """)
    print(f"Stripped time from sim_resource_allocations.release_datetime for {cur.rowcount} rows.")

    # -------------------------------------------------------------------------
    # CREATED_AT consistency — strip time-of-day from any business table
    # whose created_at column was written before the date-only fix landed.
    # All these are simulation-time dates (the in-simulation business date
    # when the row was generated), not wall-clock time.
    # -------------------------------------------------------------------------

    for tbl in ('Project_Plan', 'Project_Billing_Rate', 'Deliverable',
                'Deliverable_Title_Plan_Mapping', 'Actual_Project_Expense'):
        cur.execute(f"""
            UPDATE {tbl}
            SET created_at = DATE(created_at)
            WHERE created_at IS NOT NULL AND created_at LIKE '% %'
        """)
        if cur.rowcount > 0:
            print(f"Stripped time from {tbl}.created_at for {cur.rowcount} rows.")

    # -------------------------------------------------------------------------
    # ACTUAL_PROJECT_EXPENSE DATE
    # The DES trigger stamps created_at at the moment the expense is generated.
    # Copy it to the Date column when Date is not already set.
    # -------------------------------------------------------------------------

    cur.execute("""
        UPDATE Actual_Project_Expense
        SET Date = DATE(created_at)
        WHERE Date IS NULL AND created_at IS NOT NULL
    """)
    print(f"Updated Actual_Project_Expense.Date for {cur.rowcount} expenses.")

    conn.commit()

    # -------------------------------------------------------------------------
    # SUMMARY
    # -------------------------------------------------------------------------

    cur.execute("""
        SELECT COUNT(*),
               SUM(CASE WHEN PlannedStartDate IS NOT NULL THEN 1 ELSE 0 END),
               SUM(CASE WHEN PlannedEndDate   IS NOT NULL THEN 1 ELSE 0 END),
               SUM(CASE WHEN ActualStartDate  IS NOT NULL THEN 1 ELSE 0 END),
               SUM(CASE WHEN ActualEndDate    IS NOT NULL THEN 1 ELSE 0 END),
               SUM(CASE WHEN PlannedHours     > 0         THEN 1 ELSE 0 END),
               SUM(CASE WHEN PlannedExpense   > 0         THEN 1 ELSE 0 END),
               SUM(CASE WHEN EstimatedBudget  > 0         THEN 1 ELSE 0 END),
               ROUND(AVG(julianday(ActualStartDate) - julianday(PlannedStartDate)), 2),
               ROUND(AVG(PlannedHours), 2),
               ROUND(AVG(PlannedExpense), 2),
               ROUND(AVG(EstimatedBudget), 2)
        FROM Project_Plan
    """)
    r = cur.fetchone()
    print(f"\nProject_Plan Summary ({r[0]} projects):")
    print(f"  PlannedStartDate : {r[1]}/{r[0]}")
    print(f"  PlannedEndDate   : {r[2]}/{r[0]}")
    print(f"  ActualStartDate  : {r[3]}/{r[0]}")
    print(f"  ActualEndDate    : {r[4]}/{r[0]}")
    print(f"  Plan→Actual lag  : avg {r[8]} days  (should be roughly NORM(3,1) = onboarding_lag)")
    print(f"  PlannedHours     : {r[5]}/{r[0]}  (avg {r[9]})")
    print(f"  PlannedExpense   : {r[6]}/{r[0]}  (avg {r[10]})")
    print(f"  EstimatedBudget  : {r[7]}/{r[0]}  (avg {r[11]})")

    cur.execute("""
        SELECT COUNT(*),
               SUM(CASE WHEN PlannedStartDate    IS NOT NULL THEN 1 ELSE 0 END),
               SUM(CASE WHEN PlannedEndDate      IS NOT NULL THEN 1 ELSE 0 END),
               SUM(CASE WHEN ActualStartDate     IS NOT NULL THEN 1 ELSE 0 END),
               SUM(CASE WHEN ActualEndDate       IS NOT NULL THEN 1 ELSE 0 END),
               SUM(CASE WHEN PlannedExpense      IS NOT NULL THEN 1 ELSE 0 END),
               SUM(CASE WHEN DeliverableFixedPrice IS NOT NULL THEN 1 ELSE 0 END),
               ROUND(AVG(PlannedExpense), 2)
        FROM Deliverable
    """)
    r = cur.fetchone()
    print(f"\nDeliverable Summary ({r[0]} deliverables):")
    print(f"  PlannedStartDate     : {r[1]}/{r[0]}")
    print(f"  PlannedEndDate       : {r[2]}/{r[0]}")
    print(f"  ActualStartDate      : {r[3]}/{r[0]}")
    print(f"  ActualEndDate        : {r[4]}/{r[0]}")
    print(f"  PlannedExpense       : {r[5]}/{r[0]}  (avg {r[7]})")
    print(f"  DeliverableFixedPrice: {r[6]}/{r[0]}")

    cur.execute("""
        SELECT COUNT(*), SUM(CASE WHEN Date IS NOT NULL THEN 1 ELSE 0 END)
        FROM Actual_Project_Expense
    """)
    r = cur.fetchone()
    print(f"\nActual_Project_Expense Summary ({r[0]} expenses):")
    print(f"  Date             : {r[1]}/{r[0]}")

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <path_to_db>")
        sys.exit(1)
    calculate_financials(sys.argv[1])
