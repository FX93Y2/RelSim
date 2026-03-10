"""
Post-processing script to populate the Deliverable_Progress_Month table.

Generates monthly progress records for each deliverable based on actual
date ranges from the Consultant_Deliverable_Mapping table. Progress
increases linearly from 0% at start to 100% at completion.

Usage:
    CONSULTING_DB_PATH=output/consulting.db python generate_progress_months.py

Can also be imported and called programmatically:
    from generate_progress_months import populate_progress_months
    populate_progress_months('/path/to/database.db')
"""

import sqlite3
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta

# Default configuration
DEFAULT_DB_PATH = 'output/consulting.db'


def populate_progress_months(db_path):
    """
    Populate the Deliverable_Progress_Month table from simulation data.

    Reads each deliverable's actual date range from Consultant_Deliverable_Mapping,
    then generates one row per month with linearly interpolated PercentageComplete.

    Args:
        db_path: Path to the SQLite database

    Returns:
        int: Number of rows inserted, or -1 on error
    """
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return -1

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Check if the table exists
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Deliverable_Progress_Month'")
    if not cur.fetchone():
        print("Warning: Deliverable_Progress_Month table not found.")
        conn.close()
        return -1

    # Clear existing data
    cur.execute("DELETE FROM Deliverable_Progress_Month")

    # Get each deliverable's actual date range from the Deliverable table
    try:
        cur.execute("""
            SELECT DeliverableID, ActualStartDate, ActualEndDate
            FROM Deliverable
            WHERE ActualStartDate IS NOT NULL
              AND ActualEndDate IS NOT NULL
        """)
        deliverables = cur.fetchall()
    except sqlite3.OperationalError as e:
        print(f"Error querying deliverable date ranges: {e}")
        conn.close()
        return -1

    if not deliverables:
        print("No deliverables with consultant mappings found.")
        conn.close()
        return 0

    # Check table columns
    cur.execute("PRAGMA table_info(Deliverable_Progress_Month)")
    columns = [row[1] for row in cur.fetchall()]

    total_rows = 0
    row_id = 1

    for deliv_id, start_str, end_str in deliverables:
        if not start_str or not end_str:
            continue

        # Parse dates (handle both datetime and date-only formats)
        try:
            start = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            try:
                start = datetime.strptime(start_str[:10], '%Y-%m-%d')
            except (ValueError, AttributeError):
                continue

        try:
            end = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            try:
                end = datetime.strptime(end_str[:10], '%Y-%m-%d')
            except (ValueError, AttributeError):
                continue

        total_days = (end - start).days
        if total_days <= 0:
            total_days = 1

        # Generate one row per month from start to end
        current = start.replace(day=1)
        end_month = end.replace(day=1)

        while current <= end_month:
            days_elapsed = max(0, (current - start).days)
            pct = min(100.0, round((days_elapsed / total_days) * 100, 2))

            if 'id' in columns and 'event_type' in columns:
                cur.execute(
                    "INSERT INTO Deliverable_Progress_Month "
                    "(id, DeliverableID, Report_Month, PercentageComplete, event_type) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (row_id, deliv_id, current.strftime('%Y-%m-%d'), pct, 'progress_update')
                )
            elif 'id' in columns:
                cur.execute(
                    "INSERT INTO Deliverable_Progress_Month "
                    "(id, DeliverableID, Report_Month, PercentageComplete) "
                    "VALUES (?, ?, ?, ?)",
                    (row_id, deliv_id, current.strftime('%Y-%m-%d'), pct)
                )
            else:
                cur.execute(
                    "INSERT INTO Deliverable_Progress_Month "
                    "(DeliverableID, Report_Month, PercentageComplete) "
                    "VALUES (?, ?, ?)",
                    (deliv_id, current.strftime('%Y-%m-%d'), pct)
                )

            row_id += 1
            total_rows += 1
            current += relativedelta(months=1)

    conn.commit()
    conn.close()

    print(f"Generated {total_rows} progress month records for {len(deliverables)} deliverables.")
    print(f"  Average months per deliverable: {total_rows / len(deliverables):.1f}")

    return total_rows


def main():
    """CLI entry point."""
    db_path = os.environ.get('CONSULTING_DB_PATH', DEFAULT_DB_PATH)
    result = populate_progress_months(db_path)
    if result < 0:
        print("Progress month generation failed.")
    elif result == 0:
        print("No records generated.")
    else:
        print(f"Progress month generation complete. {result} records inserted.")


if __name__ == '__main__':
    main()
