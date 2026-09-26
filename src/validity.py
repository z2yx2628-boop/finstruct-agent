"""When is a relationship or a risk signal in force?

A 2024 related-party estimate says nothing about 2026 trade; a guarantee that ended in June
2024 cannot transmit risk in 2026; a maintenance stop is over once the furnace restarts.
Every edge and signal gets [valid_from, valid_to]; propagation only uses what is in force on
the evaluation date. Windows come from the announcement when it states them, otherwise from
fixed defaults written here (documented in docs/chain_interface.md).
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

DEFAULT_MONTHS = {
    "guarantee_limit": 12,        # annual guarantee quotas are approved for about a year
    "guarantee_provided": 36,     # typical loan term when the contract end is not stated
    "guarantee_overdue": 36,
    "related_estimate": 12,       # when the estimate year is missing
    "project": 12,                # delay / suspension / capacity change stays relevant a year
    "credit_event": 24,
    "share_pledge": 12,
    "maintenance": 3,             # when neither restart date nor duration is disclosed
}


def add_months(day: str, months: int) -> str:
    d = date.fromisoformat(day)
    month = d.month - 1 + months
    year, month = d.year + month // 12, month % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1])).isoformat()


def add_days(day: str, days: float) -> str:
    return (date.fromisoformat(day) + timedelta(days=int(round(days)))).isoformat()


def valid(day: str | None) -> bool:
    try:
        date.fromisoformat(day or "")
        return True
    except ValueError:
        return False


def window(start: str | None, end: str | None, announced: str, months: int) -> tuple[str, str]:
    """Stated dates win; otherwise [announcement, announcement + default months]."""
    frm = start if valid(start) else announced
    if valid(end):
        return frm, end
    base = frm if valid(frm) else announced
    return frm, add_months(base, months) if valid(base) else ""


def guarantee_window(event: dict, announced: str) -> tuple[str, str]:
    kind = event.get("event_type") or "guarantee_provided"
    return window(event.get("start_date"), event.get("end_date"), announced, DEFAULT_MONTHS.get(kind, 36))


def related_window(estimate_year, announced: str) -> tuple[str, str]:
    if estimate_year:
        return announced, f"{int(estimate_year)}-12-31"
    return window(None, None, announced, DEFAULT_MONTHS["related_estimate"])


def maintenance_window(event: dict, announced: str) -> tuple[str, str]:
    start = event.get("shutdown_start_date") if valid(event.get("shutdown_start_date")) else announced
    if valid(event.get("expected_restart_date")):
        return start, event["expected_restart_date"]
    if event.get("shutdown_days") and valid(start):
        return start, add_days(start, float(event["shutdown_days"]))
    return window(start, None, announced, DEFAULT_MONTHS["maintenance"])


def pledge_window(event: dict, announced: str) -> tuple[str, str]:
    end = event.get("release_date") or event.get("extended_end_date") or event.get("pledge_end_date")
    return window(event.get("pledge_start_date"), end, announced, DEFAULT_MONTHS["share_pledge"])


def is_active(row: dict, as_of: str) -> bool:
    """In force on as_of. Rows without dates (industry links) are always in force; rows built
    before validity existed fall back to "published on or before as_of"."""
    start = row.get("valid_from") or row.get("announcement_date") or row.get("date") or ""
    end = row.get("valid_to") or ""
    return (not start or start <= as_of) and (not end or as_of <= end)
