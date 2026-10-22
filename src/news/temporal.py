"""Conservative calendar chronology. Unknown dates are never imputed."""
from __future__ import annotations

import calendar
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone


@dataclass(frozen=True)
class DateValue:
    original: str
    normalized: str | None
    precision: str
    timezone: str | None
    status: str

    def to_dict(self) -> dict:
        return asdict(self)


def parse_date(value: str | None) -> DateValue:
    original = str(value or "")
    text = original.strip()
    if not text:
        return DateValue(original, None, "unknown", None, "missing")
    try:
        parsed = date.fromisoformat(text)
        return DateValue(original, parsed.isoformat(), "day", None, "valid")
    except ValueError:
        pass
    try:
        # Python 3.10 also accepts explicit offsets after replacing Z.
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00").replace(" UTC", "+00:00"))
        if parsed.tzinfo:
            return DateValue(original, parsed.astimezone(timezone.utc).isoformat(),
                             "second", str(parsed.tzinfo), "valid")
        return DateValue(original, parsed.isoformat(), "second", None, "timezone_unknown")
    except ValueError:
        return DateValue(original, None, "unknown", None, "invalid")


def add_calendar_year(value: str) -> str:
    parsed = datetime.fromisoformat(value) if "T" in value else date.fromisoformat(value)
    day = min(parsed.day, calendar.monthrange(parsed.year + 1, parsed.month)[1])
    return parsed.replace(year=parsed.year + 1, day=day).isoformat()


def compare(left: DateValue, right: DateValue) -> int | None:
    if not left.normalized or not right.normalized:
        return None
    if left.timezone and right.timezone:
        a, b = datetime.fromisoformat(left.normalized), datetime.fromisoformat(right.normalized)
    else:
        a, b = date.fromisoformat(left.normalized[:10]), date.fromisoformat(right.normalized[:10])
        # A missing timezone could cross a day boundary. Do not invent ordering.
        if (left.precision == "second" and not left.timezone) or (right.precision == "second" and not right.timezone):
            return None
        if a == b:
            return None
    return (a > b) - (a < b)


def classify_episode(t0: str, *, article_published_at: str | None,
                     event_occurred_at: str | None, first_public_disclosure_at: str | None) -> dict:
    start = parse_date(t0)
    if not start.normalized:
        raise ValueError("Invalid t0")
    end = parse_date(add_calendar_year(start.normalized))
    published, occurred, disclosed = map(parse_date, (article_published_at, event_occurred_at,
                                                     first_public_disclosure_at))
    result = {"t0": start.to_dict(), "window_end": end.to_dict(), "window": "(t0, window_end]",
              "article_published_at": published.to_dict(), "event_occurred_at": occurred.to_dict(),
              "first_public_disclosure_at": disclosed.to_dict(), "eligible": False}
    if any(compare(d, start) in (-1, 0) for d in (occurred, disclosed)):
        relation = "prior_or_already_known"
    elif not occurred.normalized or not disclosed.normalized:
        relation = "unknown_event_or_disclosure_date"
    elif any(compare(d, start) is None or compare(d, end) is None for d in (occurred, disclosed, published)):
        relation = "ambiguous_sequence"
    elif all(compare(d, start) == 1 and compare(d, end) in (-1, 0) for d in (occurred, disclosed, published)):
        relation = "new_within_window"
        result["eligible"] = True  # Temporal only; coverage, exposure and confirmation remain separate.
    else:
        relation = "outside_window"
    result["temporal_relation"] = relation
    return result


def months_between(start: str, end: str) -> list[str]:
    year, month = map(int, start[:7].split("-"))
    months = []
    while f"{year:04}-{month:02}" <= end[:7]:
        months.append(f"{year:04}-{month:02}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return months


def audit_window(t0: str, observed_months: list[str], available_until: str | None,
                 *, partial: bool = True) -> dict:
    end = add_calendar_year(t0)
    expected = months_between(t0, end)
    missing = sorted(set(expected) - set(observed_months))
    followup = ("unknown" if not available_until else
                "truncated" if available_until[:10] < end[:10] else "date_range_reaches_end")
    return {"t0": t0, "window_end": end, "observed_months": sorted(set(expected) & set(observed_months)),
            "missing_months": missing, "temporal_followup": followup,
            "search_coverage": "insufficient" if partial or missing or followup == "truncated" else "unknown",
            "eligible_for_complete_followup_comparison": False,
            "limitation": "Months and extrema do not establish sufficient search; protocol review required"}
