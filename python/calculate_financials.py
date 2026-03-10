"""
Post-processing: Calculate derived Project financial fields.

Populates the following Project columns from deliverable and billing data:
- PlannedEndDate: MAX(Deliverable.PlannedEndDate) for each project
- PlannedHours:   SUM(Deliverable_Title_Plan_Mapping.PlannedHours) for each project
- EstimatedBudget: SUM(PlannedHours * BillingRate) + SUM(PlannedExpense)

Usage:
  python calculate_financials.py <path_to_db>
"""

import sys
import sqlite3


def calculate_financials(db_path: str) -> None:
    """Calculate derived financial fields on the Project table."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1. PlannedEndDate = MAX of all deliverable PlannedEndDates per project
    cur.execute("""
        UPDATE Project_Plan
        SET PlannedEndDate = (
            SELECT MAX(d.PlannedEndDate)
            FROM Deliverable d
            WHERE d.ProjectID = Project_Plan.ProjectID
              AND d.PlannedEndDate IS NOT NULL
        )
        WHERE EXISTS (
            SELECT 1 FROM Deliverable d
            WHERE d.ProjectID = Project_Plan.ProjectID
              AND d.PlannedEndDate IS NOT NULL
        )
    """)
    planned_end_count = cur.rowcount
    print(f"Updated PlannedEndDate for {planned_end_count} projects.")

    # 2. PlannedHours = SUM of PlannedHours from Deliverable_Title_Plan_Mapping
    #    via the deliverables belonging to each project
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
    planned_hours_count = cur.rowcount
    print(f"Updated PlannedHours for {planned_hours_count} projects.")

    # 3. EstimatedBudget = SUM(PlannedHours * BillingRate) + SUM(PlannedExpense)
    #    For each project: sum across all deliverables and their title plan mappings,
    #    multiplied by the corresponding project billing rate for each title.
    cur.execute("""
        UPDATE Project_Plan
        SET EstimatedBudget = (
            SELECT COALESCE(labor.total_labor, 0) + COALESCE(expense.total_expense, 0)
            FROM (
                SELECT d.ProjectID,
                       SUM(dtpm.PlannedHours * COALESCE(pbr.BillingRate, 0)) as total_labor
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
                       SUM(COALESCE(d2.PlannedExpense, 0)) as total_expense
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
    budget_count = cur.rowcount
    print(f"Updated EstimatedBudget for {budget_count} projects.")

    conn.commit()

    # Print summary
    cur.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN PlannedEndDate IS NOT NULL THEN 1 ELSE 0 END) as has_end_date,
               SUM(CASE WHEN PlannedHours IS NOT NULL AND PlannedHours > 0 THEN 1 ELSE 0 END) as has_hours,
               SUM(CASE WHEN EstimatedBudget IS NOT NULL AND EstimatedBudget > 0 THEN 1 ELSE 0 END) as has_budget,
               ROUND(AVG(PlannedHours), 2) as avg_hours,
               ROUND(AVG(EstimatedBudget), 2) as avg_budget
        FROM Project_Plan
    """)
    row = cur.fetchone()
    if row:
        print(f"\nProject Financial Summary:")
        print(f"  Total projects: {row[0]}")
        print(f"  With PlannedEndDate: {row[1]}")
        print(f"  With PlannedHours: {row[2]}")
        print(f"  With EstimatedBudget: {row[3]}")
        print(f"  Avg PlannedHours: {row[4]}")
        print(f"  Avg EstimatedBudget: {row[5]}")

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <path_to_db>")
        sys.exit(1)
    calculate_financials(sys.argv[1])
