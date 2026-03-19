"""
Script: generates title history rows for each Consultant.
Each consultant starts at a weighted random title and may receive 0-2 promotions.
Dates are chained first-of-month values. Salary is normally distributed per title.
"""
import random
from datetime import date


# Salary params by title rank index (0=lowest title, 5=highest)
SALARY_BY_RANK = [
    (100000, 10000),   # rank 0: Consultant
    (120000, 10000),   # rank 1: Senior Consultant
    (140000, 10000),   # rank 2: Manager
    (160000, 20000),   # rank 3: Senior Manager
    (180000, 20000),   # rank 4: Associate Partner
    (200000, 20000),   # rank 5: Partner
]

# Weighted distribution for initial title rank (0-based index)
INITIAL_RANK_WEIGHTS = [
    (0, 0.30),
    (1, 0.30),
    (2, 0.20),
    (3, 0.10),
    (4, 0.05),
    (5, 0.05),
]


def add_months(d, n):
    """Add n months to date d, returning first of that month."""
    total_months = d.year * 12 + (d.month - 1) + n
    year = total_months // 12
    month = total_months % 12 + 1
    return date(year, month, 1)


def pick_initial_rank():
    """Pick initial title rank using weighted distribution."""
    r = random.random()
    cumulative = 0.0
    for rank, weight in INITIAL_RANK_WEIGHTS:
        cumulative += weight
        if r < cumulative:
            return rank
    return INITIAL_RANK_WEIGHTS[-1][0]


def random_first_of_month(start, end):
    """Pick a random first-of-month date between start and end (inclusive)."""
    months = []
    current = date(start.year, start.month, 1)
    end_first = date(end.year, end.month, 1)
    while current <= end_first:
        months.append(current)
        current = add_months(current, 1)
    return random.choice(months)


def generate_salary(rank):
    """Generate salary from normal distribution based on title rank."""
    mean, std = SALARY_BY_RANK[rank]
    return round(random.gauss(mean, std), 2)


def generate(context):
    """Generate title history rows for all consultants."""
    Consultant = context.models['Consultant']
    Title = context.models['Title']

    consultants = context.session.query(Consultant).all()
    # Get title IDs sorted by TitleID (ascending = lowest to highest rank)
    titles = context.session.query(Title).order_by(Title.TitleID).all()
    title_ids = [t.TitleID for t in titles]
    num_titles = len(title_ids)

    context.logger.info(f"Generating title history for {len(consultants)} consultants, {num_titles} title levels")

    rows = []
    for consultant in consultants:
        initial_rank = pick_initial_rank()
        max_promos = min(2, num_titles - 1 - initial_rank)
        num_promos = random.randint(0, max_promos)

        start_date = random_first_of_month(date(2020, 1, 1), date(2025, 1, 1))
        cap_date = date(2025, 12, 1)

        for i in range(num_promos + 1):
            rank = initial_rank + i
            title_id = title_ids[rank]
            salary = generate_salary(rank)

            is_last_row = (i == num_promos)

            if is_last_row:
                # 75% chance EndDate is None (still active), 25% ended
                if random.random() < 0.75:
                    end_date = None
                else:
                    months_tenure = random.randint(6, 24)
                    end_date = add_months(start_date, months_tenure)
                    if end_date > cap_date:
                        end_date = cap_date
            else:
                # Must have an end date to chain to next promotion
                months_tenure = random.randint(6, 24)
                end_date = add_months(start_date, months_tenure)
                if end_date > cap_date:
                    end_date = cap_date

            rows.append({
                "ConsultantID": consultant.ConsultantID,
                "TitleID": title_id,
                "StartDate": str(start_date),
                "EndDate": str(end_date) if end_date else None,
                "Salary": salary,
            })

            if end_date is None or end_date >= cap_date:
                break

            start_date = end_date

    context.logger.info(f"Generated {len(rows)} title history rows")
    return rows
