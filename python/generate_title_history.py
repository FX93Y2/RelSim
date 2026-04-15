"""
Post-processing script to populate the Consultant_Title_History table.

Implements the complex promotion-chain logic:
- Each consultant gets 1-3 rows depending on number of promotions (0-2)
- Initial title assigned with weighted distribution
- Dates are always on the 1st of the month
- Salary follows normal distribution based on title level
- Promotion chains are sequential (Row N+1 starts where Row N ends)

Usage:
    CONSULTING_DB_PATH=output/consulting.db python generate_title_history.py

Can also be imported and called programmatically:
    from generate_title_history import populate_title_history
    populate_title_history('/path/to/database.db')
"""

import sqlite3
import random
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta

# Default configuration
DEFAULT_DB_PATH = 'output/consulting.db'
RANDOM_SEED = 42

# Default title salary ranges: (salary_mean, salary_std)
DEFAULT_TITLE_SALARIES = [
    (100_000, 10_000),   # Level 1: Consultant
    (120_000, 10_000),   # Level 2: Senior Consultant
    (140_000, 10_000),   # Level 3: Manager
    (160_000, 20_000),   # Level 4: Senior Manager
    (180_000, 20_000),   # Level 5: Associate Partner
    (200_000, 20_000),   # Level 6: Partner
]

# Default initial title distribution weights
DEFAULT_TITLE_WEIGHTS = [0.30, 0.30, 0.20, 0.10, 0.05, 0.05]

# Date range for the simulation period
DATE_START = datetime(2020, 1, 1)
DATE_END = datetime(2025, 12, 1)


def first_of_month(dt):
    """Return the first of the month for a given datetime."""
    return dt.replace(day=1)


def random_first_of_month(start, end):
    """Return a random date that is the 1st of some month between start and end."""
    months_between = (end.year - start.year) * 12 + (end.month - start.month)
    if months_between <= 0:
        return first_of_month(start)
    random_months = random.randint(0, months_between)
    return first_of_month(start + relativedelta(months=random_months))


def generate_salary(title_salary_map, title_id):
    """Generate a salary based on title-specific normal distribution."""
    mean, std = title_salary_map[title_id]
    salary = random.gauss(mean, std)
    return round(max(salary, mean - 2 * std), 2)


def weighted_choice(title_ids, weights):
    """Pick a title ID using weighted random selection."""
    return random.choices(title_ids, weights=weights, k=1)[0]


def generate_title_history(consultant_id, title_ids, title_salary_map, title_weights):
    """
    Generate 1-3 title history rows for a single consultant.

    Returns list of tuples: (ConsultantID, TitleID, StartDate_str, EndDate_str_or_None, Salary)
    """
    num_promos = random.choices([0, 1, 2], weights=[0.34, 0.33, 0.33], k=1)[0]

    initial_title_id = weighted_choice(title_ids, title_weights)

    max_title_id = max(title_ids)
    num_promos = min(num_promos, max_title_id - initial_title_id)
    num_promos = max(num_promos, 0)

    # Build rows internally with datetime objects, convert to strings at the end
    internal_rows = []  # List of (ConsultantID, TitleID, start_dt, end_dt_or_None, Salary)
    current_title_id = initial_title_id

    for i in range(num_promos + 1):
        is_last_row = (i == num_promos)

        if i == 0:
            start_date = random_first_of_month(DATE_START, datetime(2025, 1, 1))
        else:
            start_date = internal_rows[-1][3]  # Previous EndDate (datetime object)
            if start_date is None:
                break

        if is_last_row:
            # Last row: 75% chance still active (NULL end date)
            if random.random() < 0.75:
                end_date = None
            else:
                months_ahead = random.randint(6, 24)
                end_date = first_of_month(start_date + relativedelta(months=months_ahead))
                if end_date > DATE_END:
                    end_date = DATE_END
        else:
            months_ahead = random.randint(6, 24)
            end_date = first_of_month(start_date + relativedelta(months=months_ahead))
            if end_date > DATE_END:
                end_date = DATE_END

        salary = generate_salary(title_salary_map, current_title_id)

        internal_rows.append((
            consultant_id,
            current_title_id,
            start_date,
            end_date,
            salary
        ))

        current_title_id = min(current_title_id + 1, max_title_id)

    # Convert datetime objects to strings for output
    output_rows = []
    for cid, tid, start_dt, end_dt, sal in internal_rows:
        output_rows.append((
            cid,
            tid,
            start_dt.strftime('%Y-%m-%d'),
            end_dt.strftime('%Y-%m-%d') if end_dt else None,
            sal
        ))

    return output_rows


def populate_title_history(db_path, seed=RANDOM_SEED):
    """
    Populate the Consultant_Title_History table in the given database.

    This is the main entry point — can be called from other scripts or
    integrated as a post-simulation hook.

    Args:
        db_path: Path to the SQLite database
        seed: Random seed for reproducibility

    Returns:
        int: Number of rows inserted, or -1 on error
    """
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return -1

    random.seed(seed)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all consultant IDs
    try:
        cursor.execute("SELECT ConsultantID FROM Consultant ORDER BY ConsultantID")
        consultant_ids = [row[0] for row in cursor.fetchall()]
    except sqlite3.OperationalError:
        try:
            cursor.execute("SELECT consultantid FROM consultant ORDER BY consultantid")
            consultant_ids = [row[0] for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            print("Error: Consultant table not found.")
            conn.close()
            return -1

    if not consultant_ids:
        print("No consultants found in database.")
        conn.close()
        return 0

    # Get all title IDs (sorted ascending)
    try:
        cursor.execute("SELECT TitleID FROM Title ORDER BY TitleID")
        title_ids = sorted([int(row[0]) for row in cursor.fetchall()])
    except sqlite3.OperationalError:
        title_ids = list(range(1, 7))

    if not title_ids:
        title_ids = list(range(1, 7))

    # Build salary map and weights for actual title IDs
    title_salary_map = {}
    title_weights = []
    for i, tid in enumerate(title_ids):
        if i < len(DEFAULT_TITLE_SALARIES):
            title_salary_map[tid] = DEFAULT_TITLE_SALARIES[i]
        else:
            title_salary_map[tid] = (200_000, 20_000)
        if i < len(DEFAULT_TITLE_WEIGHTS):
            title_weights.append(DEFAULT_TITLE_WEIGHTS[i])
        else:
            title_weights.append(0.05)

    # Clear existing data
    try:
        cursor.execute("DELETE FROM Consultant_Title_History")
    except sqlite3.OperationalError:
        print("Warning: Consultant_Title_History table not found. Skipping.")
        conn.close()
        return -1

    # Generate title history for each consultant
    all_rows = []
    for cid in consultant_ids:
        rows = generate_title_history(cid, title_ids, title_salary_map, title_weights)
        all_rows.extend(rows)

    # Detect table columns
    cursor.execute("PRAGMA table_info(Consultant_Title_History)")
    columns = [row[1] for row in cursor.fetchall()]

    # Insert rows
    for idx, (consultant_id, title_id, start_date, end_date, salary) in enumerate(all_rows, 1):
        if 'id' in columns and 'event_type' in columns:
            cursor.execute(
                "INSERT INTO Consultant_Title_History "
                "(id, ConsultantID, TitleID, StartDate, EndDate, Salary, event_type) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (idx, consultant_id, title_id, start_date, end_date, salary, 'title_assignment')
            )
        elif 'id' in columns:
            cursor.execute(
                "INSERT INTO Consultant_Title_History "
                "(id, ConsultantID, TitleID, StartDate, EndDate, Salary) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (idx, consultant_id, title_id, start_date, end_date, salary)
            )
        else:
            cursor.execute(
                "INSERT INTO Consultant_Title_History "
                "(ConsultantID, TitleID, StartDate, EndDate, Salary) "
                "VALUES (?, ?, ?, ?, ?)",
                (consultant_id, title_id, start_date, end_date, salary)
            )

    conn.commit()
    conn.close()

    # Print summary
    print(f"Generated {len(all_rows)} title history records for {len(consultant_ids)} consultants.")
    print(f"  Average records per consultant: {len(all_rows) / len(consultant_ids):.1f}")

    # Distribution summary
    promo_counts = {}
    current_cid = None
    count = 0
    for cid, *_ in all_rows:
        if cid != current_cid:
            if current_cid is not None:
                promo_counts[count] = promo_counts.get(count, 0) + 1
            current_cid = cid
            count = 1
        else:
            count += 1
    if current_cid is not None:
        promo_counts[count] = promo_counts.get(count, 0) + 1

    print(f"  Distribution of rows per consultant: {dict(sorted(promo_counts.items()))}")

    return len(all_rows)


def main():
    """CLI entry point."""
    db_path = os.environ.get('CONSULTING_DB_PATH', DEFAULT_DB_PATH)
    result = populate_title_history(db_path)
    if result < 0:
        print("Title history generation failed.")
    elif result == 0:
        print("No records generated.")
    else:
        print(f"Title history generation complete. {result} records inserted.")


if __name__ == '__main__':
    main()
