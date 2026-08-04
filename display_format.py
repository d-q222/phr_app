"""Shared date and datetime display formatting.

Extracted from `app.py` so record tables rendered outside it show dates the same way. `condition_ui`
cannot import `app` (app imports it, so that would be circular), and `body_map_ui` has the same need,
which is the third caller that earns this module rather than a copied helper.

Pure formatting only: these functions never parse for validation and never fail. A value they cannot
interpret is returned unchanged, so an unexpected stored format degrades to showing the raw text
rather than hiding a record or raising mid-render.
"""

from __future__ import annotations

from datetime import date, datetime


def format_display_date(value) -> str:
    """Render an ISO date as `Jan 15, 2026`, returning the input unchanged if it does not parse."""
    text = str(value).strip()
    if not text:
        return text
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return text
    return f"{parsed:%b} {parsed.day}, {parsed.year}"


def format_display_datetime(value) -> str:
    """Render an ISO timestamp as `8:00 AM, Jan 15, 2026`, falling back to date-only formatting."""
    text = str(value).strip()
    if not text:
        return text
    if "T" not in text and " " not in text:
        return format_display_date(text)
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return format_display_date(text)
    time_text = parsed.strftime("%I:%M %p").lstrip("0")
    return f"{time_text}, {parsed:%b} {parsed.day}, {parsed.year}"
