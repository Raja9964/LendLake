import calendar
from datetime import date


def month_start(d: date) -> date:
    return d.replace(day=1)


def month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def add_months(d: date, months: int) -> date:
    years, month_index = divmod(d.month - 1 + months, 12)
    year, month = d.year + years, month_index + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def month_range(first: date, last: date) -> list[date]:
    """Month starts from first to last, inclusive."""
    months, current = [], month_start(first)
    while current <= month_start(last):
        months.append(current)
        current = add_months(current, 1)
    return months


def batch_id(d: date) -> str:
    return f"{d:%Y-%m}"


def parse_month(value: str) -> date:
    """Accept YYYY-MM or YYYY-MM-DD and return the month start."""
    parts = value.strip().split("-")
    if len(parts) == 2:
        return date(int(parts[0]), int(parts[1]), 1)
    return month_start(date.fromisoformat(value.strip()))
