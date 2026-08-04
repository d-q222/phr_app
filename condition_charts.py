"""Frames and chart specifications for the Tracked Conditions detail view.

Imports pandas and altair; **deliberately imports no Streamlit and touches no database**. That seam
is the point: a chart returned from here is an ``alt.Chart``, which is a declarative spec, so a test
can assert on ``chart.to_dict()`` instead of driving a browser. The app's existing
``st.line_chart`` call sites cannot be checked that way at all.

Retrieval stays in ``condition_services`` (AGENTS.md section 3) and rendering stays in
``condition_ui``; every function here takes rows it was handed and returns a frame or a spec.

Colour is a medical-safety surface, not decoration
--------------------------------------------------
Every colour below encodes a ``flag`` **that the source recorded and this app stored**. Nothing is
computed from a value at render time, and a record with no flag column -- wearables -- is drawn as a
hollow mark rather than being assigned a status it does not have.

The palette was validated rather than eyeballed, which mattered: an earlier six-hue attempt put
purple and blue 1.6 ΔE apart under deuteranopia, and a later four-hue attempt could not find a grey
that was both distinguishable from the teal and above 3:1 on the app's background. The resolution is
three well-separated hues carrying *severity*, with **direction carried by mark shape** and "not
flagged" carried by a hollow mark -- so identity never rests on colour alone, which is also what the
reserved-status-palette rule requires.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isfinite

import altair as alt
import pandas as pd

# Drawn from APP_CSS custom properties so charts sit in the same palette as the page around them.
ACCENT = "#16705c"
INK = "#17211d"
MUTED = "#5f6f68"
BORDER = "#d9e1dd"

# Validated all-pairs: worst normal-vision ΔE 16.8, worst CVD ΔE 9.0 (deutan), all above 3:1 on the
# app's #f6f8f7 surface. High, Low and Abnormal deliberately share the warning hue -- they are the
# same severity, and which direction a value went is already legible from where the point sits on
# the y axis. Duplicating a hue is safer than inventing a fourth that no longer separates.
FLAG_COLORS = {
    "Normal": "#12805f",
    "High": "#c47a00",
    "Low": "#c47a00",
    "Abnormal": "#c47a00",
    "Critical": "#c0261a",
    "Unknown": MUTED,
}
# The secondary encoding. Without it, High and Low would be indistinguishable to anyone reading the
# legend rather than the axis.
FLAG_SHAPES = {
    "Normal": "circle",
    "High": "triangle-up",
    "Low": "triangle-down",
    "Abnormal": "square",
    "Critical": "diamond",
    "Unknown": "cross",
}
FLAG_ORDER = list(FLAG_COLORS)
NOT_FLAGGED = "Not flagged"

TREND_COLUMNS = ["date", "value", "record", "unit", "flag", "table"]
MEDICATION_COLUMNS = ["name", "start", "end", "status", "open_ended"]
FLAG_HISTORY_COLUMNS = ["record", "date", "flag"]
MONTHLY_COUNT_COLUMNS = ["month", "record_type", "count"]
RANGE_COLUMNS = ["period", "minimum", "maximum", "average"]
SEVERITY_COLUMNS = ["date", "title", "severity", "body_part", "note"]
FIRST_LATEST_COLUMNS = [
    "record",
    "unit",
    "first_date",
    "first_value",
    "first_flag",
    "latest_date",
    "latest_value",
    "latest_flag",
    "change",
    "results",
]
SPARKLINE_COLUMNS = ["condition", "record", "date", "value"]

_NUMERIC_FIELDS = {
    "wearable_records": ("timestamp", "value", "metric_type", "unit", None),
    "lab_results": ("lab_date", "numeric_value", "test_name", "unit", "flag"),
}
_TABLE_LABELS = {
    "lab_results": "Lab results",
    "medications": "Medications",
    "wearable_records": "Wearable records",
    "health_entries": "Health entries",
}
_DATE_FIELDS = {
    "lab_results": "lab_date",
    "medications": "start_date",
    "wearable_records": "timestamp",
    "health_entries": "entry_date",
}


def _empty(columns: list[str]) -> pd.DataFrame:
    """An empty frame that still carries its columns, so callers can filter without a key error."""

    return pd.DataFrame(columns=columns)


def _coerce_point(date_value: object, raw_value: object) -> tuple[pd.Timestamp, float] | None:
    """Parse one dated numeric reading, returning None for anything unusable.

    Booleans are rejected before ``float`` sees them: ``float(True)`` is 1.0, which would silently
    plot a checkbox as a measurement.
    """

    if date_value in (None, "") or isinstance(raw_value, bool) or raw_value in (None, ""):
        return None
    try:
        value = float(raw_value)
        parsed = pd.to_datetime(date_value, errors="raise")
    except (TypeError, ValueError, OverflowError):
        return None
    if pd.isna(parsed) or not isfinite(value):
        return None
    return parsed, value


def trend_frame(records_by_table: Mapping[str, Sequence[dict]]) -> pd.DataFrame:
    """Dated numeric readings across the mapped lab and wearable tables.

    Generalises what used to be ``condition_ui._numeric_series`` by carrying ``unit`` and ``flag``
    as well. Wearables have no flag column in the schema, so theirs is ``"Not flagged"`` -- an
    absence, never an assertion that a reading was normal.
    """

    rows = []
    for table, records in records_by_table.items():
        fields = _NUMERIC_FIELDS.get(table)
        if fields is None:
            continue
        date_column, value_column, name_column, unit_column, flag_column = fields
        for record in records:
            point = _coerce_point(record.get(date_column), record.get(value_column))
            if point is None:
                continue
            parsed, value = point
            flag = record.get(flag_column) if flag_column else None
            rows.append(
                {
                    "date": parsed,
                    "value": value,
                    "record": record.get(name_column),
                    "unit": record.get(unit_column) or "",
                    "flag": str(flag) if flag else NOT_FLAGGED,
                    "table": table,
                }
            )
    if not rows:
        return _empty(TREND_COLUMNS)
    return pd.DataFrame(rows, columns=TREND_COLUMNS).sort_values("date").reset_index(drop=True)


def medication_spans(rows: Sequence[dict], as_of: object) -> pd.DataFrame:
    """One dated span per medication row, for the timeline drawn beneath a trend.

    A row with no end date is clamped to ``as_of`` and marked ``open_ended`` so the chart can show
    it running to the edge rather than inventing a stop date it does not have.
    """

    spans = []
    end_stamp = pd.to_datetime(as_of, errors="coerce")
    for record in rows:
        start = pd.to_datetime(record.get("start_date"), errors="coerce")
        if pd.isna(start):
            continue
        end = pd.to_datetime(record.get("end_date"), errors="coerce")
        open_ended = bool(pd.isna(end))
        if open_ended:
            end = end_stamp
        if pd.isna(end) or end < start:
            end = start
        spans.append(
            {
                "name": record.get("name"),
                "start": start,
                "end": end,
                "status": record.get("status") or "Unknown",
                "open_ended": open_ended,
            }
        )
    if not spans:
        return _empty(MEDICATION_COLUMNS)
    return pd.DataFrame(spans, columns=MEDICATION_COLUMNS).sort_values("start").reset_index(drop=True)


def flag_history(rows: Sequence[dict]) -> pd.DataFrame:
    """Every source-flagged lab result as one dated mark per test, for the flag strip."""

    history = []
    for record in rows:
        date_value = pd.to_datetime(record.get("lab_date"), errors="coerce")
        if pd.isna(date_value):
            continue
        history.append(
            {
                "record": record.get("test_name"),
                "date": date_value,
                "flag": str(record.get("flag") or "Unknown"),
            }
        )
    if not history:
        return _empty(FLAG_HISTORY_COLUMNS)
    return pd.DataFrame(history, columns=FLAG_HISTORY_COLUMNS).sort_values("date").reset_index(drop=True)


def monthly_counts(records_by_table: Mapping[str, Sequence[dict]]) -> pd.DataFrame:
    """How many linked records exist per calendar month, split by record type.

    Describes how consistently something was measured. It says nothing about whether the cadence
    was appropriate.
    """

    counts: dict[tuple[pd.Timestamp, str], int] = {}
    for table, records in records_by_table.items():
        date_column = _DATE_FIELDS.get(table)
        if date_column is None:
            continue
        label = _TABLE_LABELS.get(table, table)
        for record in records:
            parsed = pd.to_datetime(record.get(date_column), errors="coerce")
            if pd.isna(parsed):
                continue
            key = (parsed.to_period("M").to_timestamp(), label)
            counts[key] = counts.get(key, 0) + 1
    if not counts:
        return _empty(MONTHLY_COUNT_COLUMNS)
    rows = [{"month": month, "record_type": label, "count": count} for (month, label), count in counts.items()]
    return pd.DataFrame(rows, columns=MONTHLY_COUNT_COLUMNS).sort_values(["month", "record_type"]).reset_index(drop=True)


# Finest to coarsest. A twice-weekly wearable has a real spread inside a single month; a quarterly
# lab does not, and bucketing it monthly produces a band collapsed onto its own mean -- a chart that
# looks like data but says nothing the plain trend did not. Widening the bucket until readings
# actually share one keeps the section meaningful for sparse series instead of empty.
RANGE_PERIODS = (("M", "month"), ("Q", "quarter"), ("Y", "year"))


def choose_range_period(frame: pd.DataFrame, record_name: str) -> tuple[str, str] | None:
    """Finest bucket in which this series has at least one period holding two or more readings."""

    if frame.empty:
        return None
    subset = frame[frame["record"] == record_name]
    if subset.empty:
        return None
    for code, label in RANGE_PERIODS:
        if subset.groupby(subset["date"].dt.to_period(code)).size().max() >= 2:
            return code, label
    return None


def series_with_a_visible_range(frame: pd.DataFrame) -> list[str]:
    """Series that have a spread to show at some bucket size, densest first."""

    if frame.empty:
        return []
    totals = frame["record"].value_counts()
    qualifying = [
        str(record)
        for record in frame["record"].dropna().unique()
        if choose_range_period(frame, record) is not None
    ]
    return sorted(qualifying, key=lambda record: (-int(totals.get(record, 0)), str(record)))


def value_ranges(frame: pd.DataFrame, record_name: str, period: str = "M") -> pd.DataFrame:
    """Lowest, highest and mean per period for one series.

    A dense line of several hundred readings hides its own spread; this is the view where a metric
    that swings between two values looks different from one that sits still.
    """

    if frame.empty:
        return _empty(RANGE_COLUMNS)
    subset = frame[frame["record"] == record_name]
    if subset.empty:
        return _empty(RANGE_COLUMNS)
    buckets = subset["date"].dt.to_period(period).dt.to_timestamp()
    grouped = subset.assign(period=buckets).groupby("period")["value"]
    ranges = grouped.agg(minimum="min", maximum="max", average="mean").reset_index()
    ranges["average"] = ranges["average"].round(2)
    return ranges[RANGE_COLUMNS].sort_values("period").reset_index(drop=True)


def severity_frame(rows: Sequence[dict]) -> pd.DataFrame:
    """Dated symptom entries carrying a 1-10 severity the person recorded themselves."""

    entries = []
    for record in rows:
        parsed = pd.to_datetime(record.get("entry_date"), errors="coerce")
        severity = record.get("severity")
        if pd.isna(parsed) or severity in (None, ""):
            continue
        try:
            severity_value = int(severity)
        except (TypeError, ValueError):
            continue
        entries.append(
            {
                "date": parsed,
                "title": record.get("title"),
                "severity": severity_value,
                "body_part": record.get("body_part") or "",
                "note": record.get("note") or "",
            }
        )
    if not entries:
        return _empty(SEVERITY_COLUMNS)
    return pd.DataFrame(entries, columns=SEVERITY_COLUMNS).sort_values("date").reset_index(drop=True)


def first_latest(frame: pd.DataFrame) -> pd.DataFrame:
    """Earliest and most recent reading per series, with the arithmetic difference between them.

    ``change`` is subtraction over two stored numbers, which is why it is safe to show. It is not
    labelled better or worse anywhere, because the app has no basis for either word.
    """

    if frame.empty:
        return _empty(FIRST_LATEST_COLUMNS)
    summaries = []
    for record, group in frame.groupby("record", sort=True):
        ordered = group.sort_values("date")
        first, latest = ordered.iloc[0], ordered.iloc[-1]
        summaries.append(
            {
                "record": record,
                "unit": latest["unit"],
                "first_date": first["date"],
                "first_value": first["value"],
                "first_flag": first["flag"],
                "latest_date": latest["date"],
                "latest_value": latest["value"],
                "latest_flag": latest["flag"],
                "change": round(float(latest["value"]) - float(first["value"]), 2),
                "results": int(len(ordered)),
            }
        )
    return pd.DataFrame(summaries, columns=FIRST_LATEST_COLUMNS)


def sparkline_frame(series_by_condition: Mapping[str, Sequence[dict]]) -> pd.DataFrame:
    """Flatten pre-fetched primary series into one long frame for the faceted overview.

    Takes rows rather than fetching them: keeping this module free of database access is what lets
    every chart here be tested without a fixture. ``condition_services`` owns the query.
    """

    rows = []
    for condition, records in series_by_condition.items():
        for record in records:
            date_value = record.get("date")
            point = _coerce_point(date_value, record.get("value"))
            if point is None:
                continue
            parsed, value = point
            rows.append({"condition": condition, "record": record.get("record"), "date": parsed, "value": value})
    if not rows:
        return _empty(SPARKLINE_COLUMNS)
    return pd.DataFrame(rows, columns=SPARKLINE_COLUMNS).sort_values(["condition", "date"]).reset_index(drop=True)


# --- chart specifications ------------------------------------------------------------------------


def present_flags(frame: pd.DataFrame) -> list[str]:
    """The flags actually present, in the canonical order.

    The legend lists only these. Showing all six regardless would put four entries with no marks
    beside them under most charts, which reads as missing data rather than as an unused vocabulary.
    Restricting the *domain* while keeping each flag's own colour means a flag never changes hue
    depending on which others happen to be on screen -- colour follows the flag, not its position.
    """

    if frame.empty or "flag" not in frame:
        return list(FLAG_ORDER)
    seen = set(frame["flag"].dropna())
    return [flag for flag in FLAG_ORDER if flag in seen] or list(FLAG_ORDER)


def _flag_color(domain: Sequence[str]) -> alt.Color:
    """Colour by stored flag against an explicit domain.

    The domain is spelled out so an unexpected flag value falls outside the scale and renders in
    Vega's default rather than silently borrowing the hue of a flag it is not.
    """

    return alt.Color(
        "flag:N",
        title="Source flag",
        scale=alt.Scale(domain=list(domain), range=[FLAG_COLORS[flag] for flag in domain]),
        legend=alt.Legend(orient="bottom"),
    )


def _flag_shape(domain: Sequence[str]) -> alt.Shape:
    return alt.Shape(
        "flag:N",
        title="Source flag",
        scale=alt.Scale(domain=list(domain), range=[FLAG_SHAPES[flag] for flag in domain]),
        legend=alt.Legend(orient="bottom"),
    )


def _value_axis(frame: pd.DataFrame) -> alt.Y:
    units = [unit for unit in frame["unit"].dropna().unique() if unit]
    title = f"Value ({units[0]})" if len(units) == 1 else "Value"
    # Not zero-based: these are physiological measurements where zero is not a meaningful baseline,
    # and forcing it would flatten every real movement into a straight line.
    return alt.Y("value:Q", title=title, scale=alt.Scale(zero=False))


def build_trend_chart(frame: pd.DataFrame, height: int = 260) -> alt.Chart:
    """Line with points coloured and shaped by their stored flag.

    Three layers rather than one: a neutral line for the path, filled marks for records that carry a
    real flag, and hollow marks for records that do not. The hollow layer is what keeps an unflagged
    wearable reading from being assigned a status it never had.
    """

    flags = present_flags(frame[frame["flag"] != NOT_FLAGGED] if not frame.empty else frame)
    base = alt.Chart(frame).encode(x=alt.X("date:T", title=None))
    tooltip = [
        alt.Tooltip("date:T", title="Date"),
        alt.Tooltip("record:N", title="Record"),
        alt.Tooltip("value:Q", title="Value"),
        alt.Tooltip("unit:N", title="Unit"),
        alt.Tooltip("flag:N", title="Source flag"),
    ]
    line = base.mark_line(color=ACCENT, strokeWidth=2, opacity=0.55).encode(
        y=_value_axis(frame), detail="record:N"
    )
    flagged = (
        base.transform_filter(alt.datum.flag != NOT_FLAGGED)
        .mark_point(filled=True, size=85, stroke="white", strokeWidth=1)
        .encode(y=_value_axis(frame), color=_flag_color(flags), shape=_flag_shape(flags), tooltip=tooltip)
    )
    unflagged = (
        base.transform_filter(alt.datum.flag == NOT_FLAGGED)
        .mark_point(filled=False, size=42, stroke=MUTED, strokeWidth=1.2, opacity=0.7)
        .encode(y=_value_axis(frame), tooltip=tooltip)
    )
    return alt.layer(line, unflagged, flagged).properties(height=height)


def build_medication_timeline(spans: pd.DataFrame, height: int = 110) -> alt.Chart:
    """One horizontal bar per medication, from start to end date.

    Drawn as its own chart so it can be concatenated *under* a trend on a shared time axis rather
    than layered into it. A second y scale on one plot is the classic way to imply a relationship
    between two measures that nothing has established -- here the axis is shared and the y encodes
    only which medication a bar belongs to.
    """

    return (
        alt.Chart(spans)
        .mark_bar(height=13, cornerRadius=4, color=ACCENT, opacity=0.75)
        .encode(
            x=alt.X("start:T", title=None),
            x2="end:T",
            y=alt.Y("name:N", title=None, sort="-x"),
            tooltip=[
                alt.Tooltip("name:N", title="Medication"),
                alt.Tooltip("start:T", title="Started"),
                alt.Tooltip("end:T", title="Recorded through"),
                alt.Tooltip("status:N", title="Status"),
            ],
        )
        .properties(height=height)
    )


def build_trend_with_medications(frame: pd.DataFrame, spans: pd.DataFrame) -> alt.Chart:
    """Trend above, medication spans below, sharing one time axis.

    The shared axis is what makes the timing readable at a glance -- and timing is all it shows.
    The caption in the UI says so outright, because the reading a viewer reaches for is causal and
    the app has no basis for that.
    """

    if spans.empty:
        return build_trend_chart(frame)
    return alt.vconcat(
        build_trend_chart(frame),
        build_medication_timeline(spans),
        spacing=8,
    ).resolve_scale(x="shared")


def build_flag_strip(history: pd.DataFrame, height: int = 150) -> alt.Chart:
    """One mark per result, tests down the side and time across, coloured by stored flag.

    Reads at a glance in a way a line chart cannot: a run of amber turning teal is visible across
    several tests at once, without anyone having to compare numbers to a range in their head.
    """

    return (
        alt.Chart(history)
        .mark_point(filled=True, size=110, stroke="white", strokeWidth=1)
        .encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("record:N", title=None),
            color=_flag_color(present_flags(history)),
            shape=_flag_shape(present_flags(history)),
            tooltip=[
                alt.Tooltip("date:T", title="Date"),
                alt.Tooltip("record:N", title="Test"),
                alt.Tooltip("flag:N", title="Source flag"),
            ],
        )
        .properties(height=height)
    )


def build_density_chart(counts: pd.DataFrame, height: int = 200) -> alt.Chart:
    """Linked records per month, stacked by record type."""

    return (
        alt.Chart(counts)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3, stroke="white", strokeWidth=1)
        .encode(
            x=alt.X("yearmonth(month):T", title=None),
            y=alt.Y("count:Q", title="Records"),
            color=alt.Color(
                "record_type:N",
                title="Record type",
                scale=alt.Scale(
                    domain=["Lab results", "Wearable records", "Medications", "Health entries"],
                    range=[ACCENT, "#7fb3a4", "#c47a00", "#6b8f9e"],
                ),
                legend=alt.Legend(orient="bottom"),
            ),
            tooltip=[
                alt.Tooltip("yearmonth(month):T", title="Month"),
                alt.Tooltip("record_type:N", title="Record type"),
                alt.Tooltip("count:Q", title="Records"),
            ],
        )
        .properties(height=height)
    )


def build_range_band_chart(ranges: pd.DataFrame, height: int = 220) -> alt.Chart:
    """Lowest-to-highest band per period with the mean drawn through it."""

    band = (
        alt.Chart(ranges)
        .mark_area(color=ACCENT, opacity=0.18)
        .encode(
            x=alt.X("period:T", title=None),
            y=alt.Y("minimum:Q", title="Value", scale=alt.Scale(zero=False)),
            y2="maximum:Q",
        )
    )
    mean_line = (
        alt.Chart(ranges)
        .mark_line(color=ACCENT, strokeWidth=2, point=alt.OverlayMarkDef(color=ACCENT, size=45))
        .encode(
            x=alt.X("period:T", title=None),
            y=alt.Y("average:Q", scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip("period:T", title="Period"),
                alt.Tooltip("minimum:Q", title="Lowest"),
                alt.Tooltip("average:Q", title="Mean"),
                alt.Tooltip("maximum:Q", title="Highest"),
            ],
        )
    )
    return alt.layer(band, mean_line).properties(height=height)


def build_severity_chart(entries: pd.DataFrame, height: int = 200) -> alt.Chart:
    """Self-recorded symptom severity over time, on the 1-10 scale the entry form uses."""

    return (
        alt.Chart(entries)
        .mark_point(filled=True, size=110, color=ACCENT, stroke="white", strokeWidth=1)
        .encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("severity:Q", title="Severity (1-10)", scale=alt.Scale(domain=[0, 10])),
            tooltip=[
                alt.Tooltip("date:T", title="Date"),
                alt.Tooltip("title:N", title="Entry"),
                alt.Tooltip("severity:Q", title="Severity"),
                alt.Tooltip("body_part:N", title="Body area"),
                alt.Tooltip("note:N", title="Note"),
            ],
        )
        .properties(height=height)
    )


def build_sparklines(frame: pd.DataFrame, columns: int = 3) -> alt.Chart:
    """One small line per condition, faceted, for the whole profile at a glance.

    Each panel gets its own y scale: these are different measurements in different units, and a
    shared scale would make one of them a flat line against another's range.
    """

    return (
        alt.Chart(frame)
        .mark_line(color=ACCENT, strokeWidth=2)
        .encode(
            x=alt.X("date:T", title=None, axis=alt.Axis(labels=False, ticks=False)),
            y=alt.Y("value:Q", title=None, scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip("condition:N", title="Condition"),
                alt.Tooltip("record:N", title="Series"),
                alt.Tooltip("date:T", title="Date"),
                alt.Tooltip("value:Q", title="Value"),
            ],
        )
        .properties(width=190, height=90)
        .facet(facet=alt.Facet("condition:N", title=None), columns=columns)
        .resolve_scale(y="independent")
    )
