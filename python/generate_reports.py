"""
Management Reports Generator for the Consulting Firm Database.

Produces 13 reports as specified in PPTX v2:

Per Consultant:
  1) Projects worked on since start of year + hours per project

Per Business Unit:
  2) Total revenue (current month & YTD)
  3) Forecasted revenue for remainder of year
  4) Forecasted profit at end of year

Per Project:
  5) Overall percentage complete
  6) Hours expended & other expenses to date
  7) Forecasted hours to complete
  8) Planned hours to complete

Per Fixed-Price Project:
  9)  Contract value
  10) Revenue to date
  11) Costs to date (payroll + expenses)
  12) Expected costs at completion
  13) Expected profit

Usage:
  python generate_reports.py <path_to_db> [output_dir]
"""

import sys
import os
import sqlite3
import csv
from datetime import datetime


def get_report_year(conn):
    """Determine the simulation year from the data."""
    cur = conn.cursor()
    cur.execute("SELECT MIN(created_at) FROM Project_Plan WHERE created_at IS NOT NULL")
    row = cur.fetchone()
    if row and row[0]:
        return datetime.fromisoformat(str(row[0]).replace('Z', '')).year
    return datetime.now().year


def get_current_month(conn):
    """Get the latest month in the simulation data."""
    cur = conn.cursor()
    cur.execute("SELECT MAX(start_date) FROM Consultant_Deliverable_Mapping WHERE start_date IS NOT NULL")
    row = cur.fetchone()
    if row and row[0]:
        dt = datetime.fromisoformat(str(row[0]).replace('Z', ''))
        return dt.year, dt.month
    year = get_report_year(conn)
    return year, 12


def write_csv(filepath, headers, rows):
    """Write rows to CSV file."""
    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    print(f"  -> {filepath} ({len(rows)} rows)")


def report_1_consultant_projects(conn, out_dir, year):
    """Report 1: For each consultant — projects worked on YTD + hours per project."""
    print("\nReport 1: Consultant Projects & Hours (YTD)")
    cur = conn.cursor()
    cur.execute("""
        SELECT c.ConsultantID, 
               t.Title,
               p.ProjectID,
               p.ProjectName,
               bu.BusinessUnitName,
               ROUND(SUM(cdm.ActualHours), 2) as TotalHours,
               MIN(cdm.start_date) as FirstWorked,
               MAX(cdm.end_date) as LastWorked
        FROM Consultant_Deliverable_Mapping cdm
        JOIN Deliverable d ON cdm.DeliverableID = d.DeliverableID
        JOIN Project_Plan p ON d.ProjectID = p.ProjectID
        JOIN Consultant c ON cdm.ConsultantID = c.ConsultantID
        JOIN Business_Unit bu ON p.BusinessUnitID = bu.BusinessUnitID
        LEFT JOIN Consultant_Title_History cth ON c.ConsultantID = cth.ConsultantID 
            AND cth.EndDate IS NULL
        LEFT JOIN Title t ON cth.TitleID = t.TitleID
        WHERE cdm.start_date >= ?
        GROUP BY c.ConsultantID, p.ProjectID
        ORDER BY c.ConsultantID, TotalHours DESC
    """, (f"{year}-01-01",))
    rows = cur.fetchall()
    headers = ["ConsultantID", "Title", "ProjectID", "ProjectName", "BusinessUnit",
               "TotalHours", "FirstWorked", "LastWorked"]
    write_csv(os.path.join(out_dir, "report_01_consultant_projects.csv"), headers, rows)


def report_2_bu_revenue(conn, out_dir, year, current_month):
    """Report 2: For each business unit — total revenue (current month & YTD)."""
    print("\nReport 2: Business Unit Revenue (Current Month & YTD)")
    cur = conn.cursor()
    cur_year, cur_mon = current_month
    cur.execute("""
        SELECT 
            bu.BusinessUnitID,
            bu.BusinessUnitName,
            ROUND(COALESCE(SUM(CASE 
                WHEN strftime('%%Y-%%m', cdm.start_date) = ? 
                THEN cdm.ActualHours * COALESCE(pbr.BillingRate, 0) 
                ELSE 0 END), 0), 2) as CurrentMonthRevenue,
            ROUND(COALESCE(SUM(CASE 
                WHEN cdm.start_date >= ?
                THEN cdm.ActualHours * COALESCE(pbr.BillingRate, 0) 
                ELSE 0 END), 0), 2) as YTDRevenue,
            COUNT(DISTINCT p.ProjectID) as ProjectCount,
            ROUND(COALESCE(SUM(cdm.ActualHours), 0), 2) as TotalHoursYTD
        FROM Business_Unit bu
        LEFT JOIN Project_Plan p ON bu.BusinessUnitID = p.BusinessUnitID
        LEFT JOIN Deliverable d ON p.ProjectID = d.ProjectID
        LEFT JOIN Consultant_Deliverable_Mapping cdm ON d.DeliverableID = cdm.DeliverableID
            AND cdm.start_date >= ?
        LEFT JOIN Consultant_Title_History cth ON cdm.ConsultantID = cth.ConsultantID
            AND cth.EndDate IS NULL
        LEFT JOIN Project_Billing_Rate pbr ON p.ProjectID = pbr.ProjectID 
            AND pbr.TitleID = cth.TitleID
        GROUP BY bu.BusinessUnitID
        ORDER BY YTDRevenue DESC
    """, (f"{cur_year}-{cur_mon:02d}", f"{year}-01-01", f"{year}-01-01"))
    rows = cur.fetchall()
    headers = ["BusinessUnitID", "BusinessUnit", "CurrentMonthRevenue", "YTDRevenue",
               "ProjectCount", "TotalHoursYTD"]
    write_csv(os.path.join(out_dir, "report_02_bu_revenue.csv"), headers, rows)


def report_3_bu_forecasted_revenue(conn, out_dir, year, current_month):
    """Report 3: For each BU — forecasted revenue for remainder of year."""
    print("\nReport 3: Business Unit Forecasted Revenue (Remainder of Year)")
    cur = conn.cursor()
    cur_year, cur_mon = current_month
    months_remaining = max(1, 12 - cur_mon)
    months_elapsed = cur_mon

    cur.execute("""
        SELECT 
            bu.BusinessUnitID,
            bu.BusinessUnitName,
            ROUND(COALESCE(SUM(cdm.ActualHours * COALESCE(pbr.BillingRate, 0)), 0), 2) as YTDRevenue,
            ROUND(COALESCE(SUM(cdm.ActualHours * COALESCE(pbr.BillingRate, 0)), 0) / ? * ?, 2) as ForecastedRemainingRevenue,
            ROUND(COALESCE(SUM(cdm.ActualHours * COALESCE(pbr.BillingRate, 0)), 0) / ? * 12, 2) as ForecastedFullYearRevenue
        FROM Business_Unit bu
        LEFT JOIN Project_Plan p ON bu.BusinessUnitID = p.BusinessUnitID
        LEFT JOIN Deliverable d ON p.ProjectID = d.ProjectID
        LEFT JOIN Consultant_Deliverable_Mapping cdm ON d.DeliverableID = cdm.DeliverableID
            AND cdm.start_date >= ?
        LEFT JOIN Consultant_Title_History cth ON cdm.ConsultantID = cth.ConsultantID
            AND cth.EndDate IS NULL
        LEFT JOIN Project_Billing_Rate pbr ON p.ProjectID = pbr.ProjectID
            AND pbr.TitleID = cth.TitleID
        GROUP BY bu.BusinessUnitID
        ORDER BY ForecastedFullYearRevenue DESC
    """, (months_elapsed, months_remaining, months_elapsed, f"{year}-01-01"))
    rows = cur.fetchall()
    headers = ["BusinessUnitID", "BusinessUnit", "YTDRevenue",
               "ForecastedRemainingRevenue", "ForecastedFullYearRevenue"]
    write_csv(os.path.join(out_dir, "report_03_bu_forecasted_revenue.csv"), headers, rows)


def report_4_bu_forecasted_profit(conn, out_dir, year, current_month):
    """Report 4: For each BU — forecasted profit at end of year."""
    print("\nReport 4: Business Unit Forecasted Profit (End of Year)")
    cur = conn.cursor()
    cur_year, cur_mon = current_month
    months_elapsed = max(1, cur_mon)

    cur.execute("""
        SELECT
            bu.BusinessUnitID,
            bu.BusinessUnitName,
            ROUND(COALESCE(rev.YTDRevenue, 0) / ? * 12, 2) as ForecastedAnnualRevenue,
            ROUND(COALESCE(costs.YTDLabor, 0) / ? * 12, 2) as ForecastedAnnualLaborCost,
            ROUND(COALESCE(costs.YTDExpenses, 0) / ? * 12, 2) as ForecastedAnnualExpenses,
            ROUND(
                (COALESCE(rev.YTDRevenue, 0) / ? * 12) -
                (COALESCE(costs.YTDLabor, 0) / ? * 12) -
                (COALESCE(costs.YTDExpenses, 0) / ? * 12), 2
            ) as ForecastedAnnualProfit
        FROM Business_Unit bu
        LEFT JOIN (
            SELECT p.BusinessUnitID,
                   SUM(cdm.ActualHours * COALESCE(pbr.BillingRate, 0)) as YTDRevenue
            FROM Project_Plan p
            JOIN Deliverable d ON p.ProjectID = d.ProjectID
            JOIN Consultant_Deliverable_Mapping cdm ON d.DeliverableID = cdm.DeliverableID
            LEFT JOIN Consultant_Title_History cth ON cdm.ConsultantID = cth.ConsultantID
                AND cth.EndDate IS NULL
            LEFT JOIN Project_Billing_Rate pbr ON p.ProjectID = pbr.ProjectID
                AND pbr.TitleID = cth.TitleID
            WHERE cdm.start_date >= ?
            GROUP BY p.BusinessUnitID
        ) rev ON bu.BusinessUnitID = rev.BusinessUnitID
        LEFT JOIN (
            SELECT p.BusinessUnitID,
                   SUM(cdm.ActualHours * 100) as YTDLabor,
                   COALESCE(SUM(pe_sub.TotalExpenses), 0) as YTDExpenses
            FROM Project_Plan p
            JOIN Deliverable d ON p.ProjectID = d.ProjectID
            JOIN Consultant_Deliverable_Mapping cdm ON d.DeliverableID = cdm.DeliverableID
            LEFT JOIN (
                SELECT DeliverableID, SUM(Amount) as TotalExpenses
                FROM Actual_Project_Expense
                GROUP BY DeliverableID
            ) pe_sub ON d.DeliverableID = pe_sub.DeliverableID
            WHERE cdm.start_date >= ?
            GROUP BY p.BusinessUnitID
        ) costs ON bu.BusinessUnitID = costs.BusinessUnitID
        ORDER BY ForecastedAnnualProfit DESC
    """, (months_elapsed, months_elapsed, months_elapsed,
          months_elapsed, months_elapsed, months_elapsed,
          f"{year}-01-01", f"{year}-01-01"))
    rows = cur.fetchall()
    headers = ["BusinessUnitID", "BusinessUnit", "ForecastedAnnualRevenue",
               "ForecastedAnnualLaborCost", "ForecastedAnnualExpenses", "ForecastedAnnualProfit"]
    write_csv(os.path.join(out_dir, "report_04_bu_forecasted_profit.csv"), headers, rows)


def report_5_project_pct_complete(conn, out_dir):
    """Report 5: For each project — overall percentage complete."""
    print("\nReport 5: Project Percentage Complete")
    cur = conn.cursor()
    cur.execute("""
        SELECT
            p.ProjectID,
            p.ProjectName,
            p.ProjectType,
            p.ProjectStatus,
            bu.BusinessUnitName,
            ROUND(COALESCE(SUM(cdm.ActualHours), 0), 2) as ActualHours,
            ROUND(COALESCE(SUM(dtpm.PlannedHours), 0), 2) as PlannedHours,
            CASE 
                WHEN COALESCE(SUM(dtpm.PlannedHours), 0) > 0 
                THEN ROUND(COALESCE(SUM(cdm.ActualHours), 0) / SUM(dtpm.PlannedHours) * 100, 1)
                ELSE 0 
            END as PctComplete
        FROM Project_Plan p
        JOIN Business_Unit bu ON p.BusinessUnitID = bu.BusinessUnitID
        LEFT JOIN Deliverable d ON p.ProjectID = d.ProjectID
        LEFT JOIN Consultant_Deliverable_Mapping cdm ON d.DeliverableID = cdm.DeliverableID
        LEFT JOIN Deliverable_Title_Plan_Mapping dtpm ON d.DeliverableID = dtpm.DeliverableID
        GROUP BY p.ProjectID
        ORDER BY PctComplete DESC
    """)
    rows = cur.fetchall()
    headers = ["ProjectID", "ProjectName", "ProjectType", "Status", "BusinessUnit",
               "ActualHours", "PlannedHours", "PctComplete"]
    write_csv(os.path.join(out_dir, "report_05_project_pct_complete.csv"), headers, rows)


def report_6_project_hours_expenses(conn, out_dir):
    """Report 6: For each project — hours expended & expenses to date."""
    print("\nReport 6: Project Hours & Expenses to Date")
    cur = conn.cursor()
    cur.execute("""
        SELECT
            p.ProjectID,
            p.ProjectName,
            p.ProjectType,
            p.ProjectStatus,
            ROUND(COALESCE(h.TotalHours, 0), 2) as HoursExpended,
            ROUND(COALESCE(e.TotalExpenses, 0), 2) as ExpensesToDate,
            ROUND(COALESCE(h.TotalHours, 0) * COALESCE(avg_rate.AvgRate, 0), 2) as LaborCostEstimate,
            ROUND(COALESCE(h.TotalHours, 0) * COALESCE(avg_rate.AvgRate, 0) 
                  + COALESCE(e.TotalExpenses, 0), 2) as TotalCostToDate
        FROM Project_Plan p
        LEFT JOIN (
            SELECT d.ProjectID, SUM(cdm.ActualHours) as TotalHours
            FROM Deliverable d
            JOIN Consultant_Deliverable_Mapping cdm ON d.DeliverableID = cdm.DeliverableID
            GROUP BY d.ProjectID
        ) h ON p.ProjectID = h.ProjectID
        LEFT JOIN (
            SELECT d.ProjectID, SUM(pe.Amount) as TotalExpenses
            FROM Deliverable d
            JOIN Actual_Project_Expense pe ON d.DeliverableID = pe.DeliverableID
            GROUP BY d.ProjectID
        ) e ON p.ProjectID = e.ProjectID
        LEFT JOIN (
            SELECT ProjectID, AVG(BillingRate) as AvgRate
            FROM Project_Billing_Rate
            GROUP BY ProjectID
        ) avg_rate ON p.ProjectID = avg_rate.ProjectID
        ORDER BY TotalCostToDate DESC
    """)
    rows = cur.fetchall()
    headers = ["ProjectID", "ProjectName", "ProjectType", "Status",
               "HoursExpended", "ExpensesToDate", "LaborCostEstimate", "TotalCostToDate"]
    write_csv(os.path.join(out_dir, "report_06_project_hours_expenses.csv"), headers, rows)


def report_7_forecasted_hours(conn, out_dir):
    """Report 7: For each project — forecasted hours to complete."""
    print("\nReport 7: Forecasted Hours to Complete")
    cur = conn.cursor()
    cur.execute("""
        SELECT
            p.ProjectID,
            p.ProjectName,
            p.ProjectType,
            p.ProjectStatus,
            ROUND(COALESCE(h.TotalActualHours, 0), 2) as ActualHoursToDate,
            ROUND(COALESCE(planned.TotalPlannedHours, 0), 2) as PlannedHours,
            CASE 
                WHEN COALESCE(planned.TotalPlannedHours, 0) > 0 
                THEN ROUND(COALESCE(h.TotalActualHours, 0) / planned.TotalPlannedHours * 100, 1)
                ELSE 0 
            END as PctComplete,
            ROUND(MAX(0, COALESCE(planned.TotalPlannedHours, 0) - COALESCE(h.TotalActualHours, 0)), 2) 
                as RemainingHours,
            CASE 
                WHEN COALESCE(h.TotalActualHours, 0) > 0 AND COALESCE(planned.TotalPlannedHours, 0) > 0
                THEN ROUND(
                    (COALESCE(h.TotalActualHours, 0) / 
                     (COALESCE(h.TotalActualHours, 0) / planned.TotalPlannedHours)) 
                    - COALESCE(h.TotalActualHours, 0), 2)
                ELSE COALESCE(planned.TotalPlannedHours, 0)
            END as ForecastedRemainingHours
        FROM Project_Plan p
        LEFT JOIN (
            SELECT d.ProjectID, SUM(cdm.ActualHours) as TotalActualHours
            FROM Deliverable d
            JOIN Consultant_Deliverable_Mapping cdm ON d.DeliverableID = cdm.DeliverableID
            GROUP BY d.ProjectID
        ) h ON p.ProjectID = h.ProjectID
        LEFT JOIN (
            SELECT d.ProjectID, SUM(dtpm.PlannedHours) as TotalPlannedHours
            FROM Deliverable d
            JOIN Deliverable_Title_Plan_Mapping dtpm ON d.DeliverableID = dtpm.DeliverableID
            GROUP BY d.ProjectID
        ) planned ON p.ProjectID = planned.ProjectID
        ORDER BY ForecastedRemainingHours DESC
    """)
    rows = cur.fetchall()
    headers = ["ProjectID", "ProjectName", "ProjectType", "Status",
               "ActualHoursToDate", "PlannedHours", "PctComplete",
               "RemainingHours", "ForecastedRemainingHours"]
    write_csv(os.path.join(out_dir, "report_07_forecasted_hours.csv"), headers, rows)


def report_8_planned_hours(conn, out_dir):
    """Report 8: For each project — planned hours to complete."""
    print("\nReport 8: Planned Hours to Complete")
    cur = conn.cursor()
    cur.execute("""
        SELECT
            p.ProjectID,
            p.ProjectName,
            p.ProjectType,
            p.ProjectStatus,
            t.TitleID,
            t.Title,
            ROUND(COALESCE(dtpm.PlannedHours, 0), 2) as PlannedHours,
            ROUND(COALESCE(actual.ActualHours, 0), 2) as ActualHours,
            ROUND(MAX(0, COALESCE(dtpm.PlannedHours, 0) - COALESCE(actual.ActualHours, 0)), 2) 
                as RemainingPlannedHours
        FROM Project_Plan p
        JOIN Deliverable d ON p.ProjectID = d.ProjectID
        JOIN Deliverable_Title_Plan_Mapping dtpm ON d.DeliverableID = dtpm.DeliverableID
        JOIN Title t ON dtpm.TitleID = t.TitleID
        LEFT JOIN (
            SELECT cdm.DeliverableID, cth.TitleID, SUM(cdm.ActualHours) as ActualHours
            FROM Consultant_Deliverable_Mapping cdm
            LEFT JOIN Consultant_Title_History cth ON cdm.ConsultantID = cth.ConsultantID
                AND cth.EndDate IS NULL
            GROUP BY cdm.DeliverableID, cth.TitleID
        ) actual ON d.DeliverableID = actual.DeliverableID AND dtpm.TitleID = actual.TitleID
        ORDER BY p.ProjectID, t.TitleID
    """)
    rows = cur.fetchall()
    headers = ["ProjectID", "ProjectName", "ProjectType", "Status",
               "TitleID", "Title", "PlannedHours", "ActualHours", "RemainingPlannedHours"]
    write_csv(os.path.join(out_dir, "report_08_planned_hours.csv"), headers, rows)


def report_9_to_13_fixed_price(conn, out_dir):
    """Reports 9-13: Fixed-price project reports."""
    print("\nReports 9-13: Fixed-Price Project Analysis")
    cur = conn.cursor()
    cur.execute("""
        SELECT
            p.ProjectID,
            p.ProjectName,
            p.ProjectStatus,
            bu.BusinessUnitName,
            -- Report 9: Contract value
            ROUND(COALESCE(p.Fixed_Price_Amount, 0), 2) as ContractValue,
            -- Report 10: Revenue to date (% complete × contract value)
            ROUND(COALESCE(p.Fixed_Price_Amount, 0) * 
                CASE WHEN COALESCE(planned.TotalPlannedHours, 0) > 0 
                     THEN MIN(1.0, COALESCE(actual.TotalActualHours, 0) / planned.TotalPlannedHours)
                     ELSE 0 END, 2) as RevenueToDate,
            -- Report 11: Costs to date (labor + expenses)
            ROUND(COALESCE(actual.TotalActualHours, 0) * COALESCE(avg_rate.AvgRate, 0), 2) as LaborCostToDate,
            ROUND(COALESCE(exp.TotalExpenses, 0), 2) as ExpensesToDate,
            ROUND(COALESCE(actual.TotalActualHours, 0) * COALESCE(avg_rate.AvgRate, 0) 
                  + COALESCE(exp.TotalExpenses, 0), 2) as TotalCostsToDate,
            -- Report 12: Expected costs at completion
            CASE WHEN COALESCE(actual.TotalActualHours, 0) > 0 
                      AND COALESCE(planned.TotalPlannedHours, 0) > 0
                 THEN ROUND(
                    (COALESCE(actual.TotalActualHours, 0) * COALESCE(avg_rate.AvgRate, 0)
                     + COALESCE(exp.TotalExpenses, 0))
                    / MIN(1.0, COALESCE(actual.TotalActualHours, 0) / planned.TotalPlannedHours), 2)
                 ELSE ROUND(COALESCE(planned.TotalPlannedHours, 0) * COALESCE(avg_rate.AvgRate, 0)
                      + COALESCE(exp.TotalExpenses, 0), 2)
            END as ExpectedCostsAtCompletion,
            -- Report 13: Expected profit
            ROUND(COALESCE(p.Fixed_Price_Amount, 0) - 
                CASE WHEN COALESCE(actual.TotalActualHours, 0) > 0 
                          AND COALESCE(planned.TotalPlannedHours, 0) > 0
                     THEN (COALESCE(actual.TotalActualHours, 0) * COALESCE(avg_rate.AvgRate, 0)
                           + COALESCE(exp.TotalExpenses, 0))
                          / MIN(1.0, COALESCE(actual.TotalActualHours, 0) / planned.TotalPlannedHours)
                     ELSE COALESCE(planned.TotalPlannedHours, 0) * COALESCE(avg_rate.AvgRate, 0)
                          + COALESCE(exp.TotalExpenses, 0)
                END, 2) as ExpectedProfit
        FROM Project_Plan p
        JOIN Business_Unit bu ON p.BusinessUnitID = bu.BusinessUnitID
        LEFT JOIN (
            SELECT d.ProjectID, SUM(cdm.ActualHours) as TotalActualHours
            FROM Deliverable d
            JOIN Consultant_Deliverable_Mapping cdm ON d.DeliverableID = cdm.DeliverableID
            GROUP BY d.ProjectID
        ) actual ON p.ProjectID = actual.ProjectID
        LEFT JOIN (
            SELECT d.ProjectID, SUM(dtpm.PlannedHours) as TotalPlannedHours
            FROM Deliverable d
            JOIN Deliverable_Title_Plan_Mapping dtpm ON d.DeliverableID = dtpm.DeliverableID
            GROUP BY d.ProjectID
        ) planned ON p.ProjectID = planned.ProjectID
        LEFT JOIN (
            SELECT d.ProjectID, SUM(pe.Amount) as TotalExpenses
            FROM Deliverable d
            JOIN Actual_Project_Expense pe ON d.DeliverableID = pe.DeliverableID
            GROUP BY d.ProjectID
        ) exp ON p.ProjectID = exp.ProjectID
        LEFT JOIN (
            SELECT ProjectID, AVG(BillingRate) as AvgRate
            FROM Project_Billing_Rate
            GROUP BY ProjectID
        ) avg_rate ON p.ProjectID = avg_rate.ProjectID
        WHERE p.ProjectType = 'Fixed-Price'
        ORDER BY ExpectedProfit DESC
    """)
    rows = cur.fetchall()
    headers = ["ProjectID", "ProjectName", "Status", "BusinessUnit",
               "ContractValue", "RevenueToDate",
               "LaborCostToDate", "ExpensesToDate", "TotalCostsToDate",
               "ExpectedCostsAtCompletion", "ExpectedProfit"]
    write_csv(os.path.join(out_dir, "report_09_13_fixed_price.csv"), headers, rows)


def generate_all_reports(db_path, out_dir):
    """Generate all 13 management reports."""
    os.makedirs(out_dir, exist_ok=True)
    conn = sqlite3.connect(db_path)

    year = get_report_year(conn)
    current_month = get_current_month(conn)
    print(f"Report Year: {year}, Current Month: {current_month[0]}-{current_month[1]:02d}")

    # Per Consultant
    report_1_consultant_projects(conn, out_dir, year)

    # Per Business Unit
    report_2_bu_revenue(conn, out_dir, year, current_month)
    report_3_bu_forecasted_revenue(conn, out_dir, year, current_month)
    report_4_bu_forecasted_profit(conn, out_dir, year, current_month)

    # Per Project
    report_5_project_pct_complete(conn, out_dir)
    report_6_project_hours_expenses(conn, out_dir)
    report_7_forecasted_hours(conn, out_dir)
    report_8_planned_hours(conn, out_dir)

    # Per Fixed-Price Project
    report_9_to_13_fixed_price(conn, out_dir)

    conn.close()
    print(f"\nAll reports saved to {out_dir}/")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <path_to_db> [output_dir]")
        sys.exit(1)

    db_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "output/reports"
    generate_all_reports(db_path, out_dir)
