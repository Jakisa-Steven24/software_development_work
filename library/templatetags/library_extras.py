from django import template

register = template.Library()


@register.filter
def star_pct(value):
    """Return the fill percentage for the star bar, 0-100."""
    try:
        rating = float(value or 0)
    except (TypeError, ValueError):
        rating = 0.0
    return round(max(0.0, min(5.0, rating)) / 5 * 100, 2)
