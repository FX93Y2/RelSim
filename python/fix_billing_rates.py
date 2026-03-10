"""
Post-processing: Fix TitleIDs and billing rates in ProjectBillingRate.

The trigger processor creates 6 rows per project but does not assign
TitleID values (they are NULL). This script:
1. Assigns TitleIDs cyclically (101-106) to each group of 6 rows per project
2. Updates billing rates with title-specific distributions per PPTX v2 Slide 16

Also fixes NULL TitleIDs in Deliverable_Title_Plan_Mapping.

Usage:
  python fix_billing_rates.py <path_to_db>
"""

import sys
import sqlite3
import random

# Title-specific billing rate distributions: {TitleID: (mean, std)}
TITLE_RATES = {
    101: (150, 20),   # Consultant
    102: (200, 20),   # Senior Consultant
    103: (250, 20),   # Manager
    104: (400, 30),   # Senior Manager
    105: (400, 30),   # Associate Partner
    106: (500, 30),   # Partner
}


def fix_billing_rates(db_path: str) -> None:
    """Assign TitleIDs and update billing rates with title-specific distributions."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Get all TitleIDs from the Title table
    cur.execute("SELECT TitleID FROM Title ORDER BY TitleID")
    title_ids = [int(row[0]) for row in cur.fetchall()]
    if not title_ids:
        title_ids = [101, 102, 103, 104, 105, 106]

    num_titles = len(title_ids)

    # === Step 1: Fix TitleIDs in ProjectBillingRate ===
    cur.execute("SELECT id, ProjectID FROM Project_Billing_Rate ORDER BY ProjectID, id")
    rows = cur.fetchall()

    if not rows:
        print("No billing rate rows found.")
        conn.close()
        return

    # Group by ProjectID and assign TitleIDs cyclically
    project_counter = {}
    updated_ids = 0
    for row_id, project_id in rows:
        idx = project_counter.get(project_id, 0)
        tid = title_ids[idx % num_titles]
        mean, std = TITLE_RATES.get(tid, (275, 50))
        rate = round(max(50.0, random.gauss(mean, std)), 2)
        cur.execute(
            "UPDATE Project_Billing_Rate SET TitleID = ?, BillingRate = ? WHERE id = ?",
            (tid, rate, row_id)
        )
        project_counter[project_id] = idx + 1
        updated_ids += 1

    print(f"Updated {updated_ids} billing rate rows ({len(project_counter)} projects × {num_titles} titles).")

    # === Step 2: Fix TitleIDs in Deliverable_Title_Plan_Mapping ===
    cur.execute("""
        SELECT _rowid, DeliverableID FROM Deliverable_Title_Plan_Mapping
        ORDER BY DeliverableID, _rowid
    """)
    dtpm_rows = cur.fetchall()

    if dtpm_rows:
        deliverable_counter = {}
        dtpm_updated = 0
        for rowid, deliv_id in dtpm_rows:
            idx = deliverable_counter.get(deliv_id, 0)
            tid = title_ids[idx % num_titles]
            cur.execute(
                "UPDATE Deliverable_Title_Plan_Mapping SET TitleID = ? WHERE _rowid = ?",
                (tid, rowid)
            )
            deliverable_counter[deliv_id] = idx + 1
            dtpm_updated += 1
        print(f"Updated {dtpm_updated} title plan mapping rows ({len(deliverable_counter)} deliverables × {num_titles} titles).")

    conn.commit()

    # Print billing rate summary
    cur.execute("""
        SELECT TitleID, COUNT(*), ROUND(AVG(BillingRate), 2),
               ROUND(MIN(BillingRate), 2), ROUND(MAX(BillingRate), 2)
        FROM Project_Billing_Rate
        GROUP BY TitleID
        ORDER BY TitleID
    """)
    print("\nBilling Rate Summary by Title:")
    print(f"{'TitleID':>8}  {'Count':>6}  {'Avg':>8}  {'Min':>8}  {'Max':>8}")
    for tid, cnt, avg, mn, mx in cur.fetchall():
        avg = avg or 0
        mn = mn or 0
        mx = mx or 0
        print(f"{tid!s:>8}  {cnt:>6}  {avg:>8.2f}  {mn:>8.2f}  {mx:>8.2f}")

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <path_to_db>")
        sys.exit(1)
    fix_billing_rates(sys.argv[1])
