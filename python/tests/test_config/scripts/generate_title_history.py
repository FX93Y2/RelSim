"""
Test script: generates title history rows for each Consultant.
Used by the scripted generation end-to-end test.
"""
import random
from datetime import date, timedelta


# Promotion ladder
TITLES = ["Analyst", "Consultant", "Senior Consultant", "Manager", "Senior Manager"]


def generate(context):
    """
    Generate a realistic title history for each consultant.
    Each consultant starts as Analyst and may be promoted 1-4 times.
    """
    Consultant = context.models['Consultant']
    consultants = context.session.query(Consultant).all()

    context.logger.info(f"Generating title history for {len(consultants)} consultants")

    rows = []
    for consultant in consultants:
        # Each consultant gets 1-4 title changes
        num_promotions = random.randint(1, min(4, len(TITLES)))
        current_date = date(2018, 1, 1) + timedelta(days=random.randint(0, 365))

        for i in range(num_promotions):
            duration_days = random.randint(365, 730)  # 1-2 years per title
            end_date = current_date + timedelta(days=duration_days)

            rows.append({
                "consultant_id": consultant.id,
                "title": TITLES[i],
                "start_date": str(current_date),
                "end_date": str(end_date),
            })

            current_date = end_date

    context.logger.info(f"Generated {len(rows)} title history rows")
    return rows
