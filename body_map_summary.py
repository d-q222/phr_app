from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from body_map_config import normalize_record_name
from body_map_services import NormalizedBodyRecord

StatusLabel = Literal[
    "No data",
    "Data available",
    "No flagged items",
    "Needs review",
    "Historical flag found",
    "Mapping uncertain",
]


@dataclass(frozen=True)
class BodyPartHealthSummary:
    """Conservative, non-diagnostic summary of profile-scoped body-map records."""

    status_label: StatusLabel
    status_reason: str
    latest_records: tuple[NormalizedBodyRecord, ...]
    current_flagged_records: tuple[NormalizedBodyRecord, ...]
    historical_flagged_records: tuple[NormalizedBodyRecord, ...]
    uncertain_mapping_records: tuple[NormalizedBodyRecord, ...]
    chronology_unknown_records: tuple[NormalizedBodyRecord, ...]
    record_counts_by_type: dict[str, int]
    latest_relevant_date: str | None


def _parsed_date(record: NormalizedBodyRecord) -> datetime | None:
    value = (record.date or "").strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _comparable_key(record: NormalizedBodyRecord) -> tuple[str, str, str, int]:
    name = normalize_record_name(record.name)
    return (
        record.record_type,
        name,
        "" if name else record.source_table,
        0 if name else record.record_id,
    )


def _flag(record: NormalizedBodyRecord) -> tuple[Literal["abnormal", "normal"] | None, str | None]:
    flag = normalize_record_name(record.status_flag or "")
    abnormal = {
        "abnormal": "abnormal",
        "high": "high",
        "h": "high",
        "low": "low",
        "l": "low",
        "critical": "critical",
    }
    if flag in abnormal:
        return "abnormal", abnormal[flag]
    if flag == "positive" and record.source_table == "lab_results":
        return "abnormal", "positive"
    if flag in {"normal", "within range", "within normal range", "negative", "not detected"}:
        return "normal", flag
    return None, None


def _flag_reason(records: Sequence[NormalizedBodyRecord], timing: str) -> str:
    if len(records) == 1:
        label = _flag(records[0])[1]
        return f"1 {timing} record is source-flagged {label}."
    return f"{len(records)} {timing} records have recognized source flags."


def summarize_body_part_health(
    records: Sequence[NormalizedBodyRecord],
) -> BodyPartHealthSummary:
    """Return a conservative summary of normalized records for one body part.

    The input is expected to come from one profile-scoped Part 2 retrieval. This function reads only
    source flags and mapping metadata; it does not interpret values or reference ranges.
    """

    source_records = tuple(records)
    counts = dict(sorted(Counter(record.record_type for record in source_records).items()))
    dated = sorted(
        ((record, parsed) for record in source_records if (parsed := _parsed_date(record)) is not None),
        key=lambda item: (item[1], item[0].source_table, item[0].record_id),
        reverse=True,
    )
    chronology_unknown = tuple(
        sorted(
            (record for record in source_records if _parsed_date(record) is None),
            key=lambda record: (
                record.record_type,
                normalize_record_name(record.name),
                record.source_table,
                record.record_id,
            ),
        )
    )

    groups: dict[tuple[str, str, str, int], list[tuple[NormalizedBodyRecord, datetime]]] = {}
    for record, parsed in dated:
        groups.setdefault(_comparable_key(record), []).append((record, parsed))

    latest = []
    historical_flagged = []
    for group in groups.values():
        latest_date = group[0][1]
        latest.extend(record for record, parsed in group if parsed == latest_date)
        historical_flagged.extend(
            record
            for record, parsed in group
            if parsed < latest_date and _flag(record)[0] == "abnormal"
        )

    latest_records = tuple(
        sorted(
            latest,
            key=lambda record: (_parsed_date(record), record.source_table, record.record_id),
            reverse=True,
        )
    )
    historical_flagged_records = tuple(
        sorted(
            historical_flagged,
            key=lambda record: (_parsed_date(record), record.source_table, record.record_id),
            reverse=True,
        )
    )
    current_flagged_records = tuple(record for record in latest_records if _flag(record)[0] == "abnormal")
    unknown_flagged = tuple(record for record in chronology_unknown if _flag(record)[0] == "abnormal")
    uncertain_mapping_records = tuple(
        record
        for record in tuple(record for record, _ in dated) + chronology_unknown
        if record.mapping_confidence == "low"
    )
    usable_flags = tuple(record for record in source_records if _flag(record)[0] is not None)
    summary_drivers = latest_records + chronology_unknown

    if not source_records:
        status: StatusLabel = "No data"
        reasons = ["No relevant records are available."]
    elif summary_drivers and all(record.mapping_confidence == "low" for record in summary_drivers):
        status = "Mapping uncertain"
        reasons = ["All latest or date-unknown relevant records have low-confidence mappings."]
    elif current_flagged_records or unknown_flagged:
        status = "Needs review"
        reasons = []
    elif historical_flagged_records:
        status = "Historical flag found"
        reasons = []
    elif usable_flags:
        status = "No flagged items"
        reasons = ["Usable source flags were found; none use a recognized abnormal flag."]
    else:
        status = "Data available"
        reasons = ["Records are available, but no usable source flags were found."]

    if current_flagged_records:
        reasons.append(_flag_reason(current_flagged_records, "latest relevant"))
    if historical_flagged_records:
        count = len(historical_flagged_records)
        reasons.append(f"{count} historical flagged record{' was' if count == 1 else 's were'} found.")
    if unknown_flagged:
        count = len(unknown_flagged)
        reasons.append(f"{count} source-flagged record{' has' if count == 1 else 's have'} unknown chronology.")
    if uncertain_mapping_records and status != "Mapping uncertain":
        count = len(uncertain_mapping_records)
        reasons.append(f"{count} record{' has a' if count == 1 else 's have'} low-confidence mapping{'s' if count != 1 else ''}.")

    return BodyPartHealthSummary(
        status_label=status,
        status_reason=" ".join(reasons),
        latest_records=latest_records,
        current_flagged_records=current_flagged_records,
        historical_flagged_records=historical_flagged_records,
        uncertain_mapping_records=uncertain_mapping_records,
        chronology_unknown_records=chronology_unknown,
        record_counts_by_type=counts,
        latest_relevant_date=dated[0][0].date if dated else None,
    )
