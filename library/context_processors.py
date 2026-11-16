"""Institution branding and circulation policy shared by every template.

Keeping the name, monogram, palette wording and borrowing rules in one place
means a deployment for another college only has to change this module (plus the
stylesheet) instead of hunting through every template.
"""
from .models import FINE_PER_DAY_UGX, LOAN_PERIOD_DAYS, MAX_UNRETURNED_BOOKS

BRAND = {
    "name": "Hillcrest Shelf",
    "institution": "Hillcrest College",
    "short_institution": "Hillcrest",
    "monogram": "HC",
    "tagline": "The college library borrowing register",
    "location": "Kampala, Uganda",
    "desk_email": "library@hillcrest.ac.ug",
    "desk_hours": "Mon–Fri, 8:00 am – 6:00 pm",
}


def branding(request):
    return {
        "brand": BRAND,
        "loan_policy": {
            "period_days": LOAN_PERIOD_DAYS,
            "max_titles": MAX_UNRETURNED_BOOKS,
            "fine_per_day": FINE_PER_DAY_UGX,
        },
    }
