"""Obsidian daily-notes data-loading for termseries."""

from __future__ import annotations

import math
import re
from datetime import date, datetime, time, timezone
from pathlib import Path

import yaml

from termseries.period import filter_period, resolve_tz
from termseries.types import TimeSeries

# ---------------------------------------------------------------------------
# Frontmatter extraction
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?\r?\n)---\r?\n", re.DOTALL)


def _extract_frontmatter(text: str, path: Path) -> dict[str, object]:
    """Return the parsed YAML frontmatter block of a note, or ``{}``.

    A note with no ``---``-delimited block at the very start of the file
    (or one whose block parses to something other than a mapping, e.g. a
    bare YAML list) has no usable fields, not an error. Only genuinely
    malformed YAML inside a real frontmatter block raises.
    """
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return {}
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise RuntimeError(f"{path}: invalid frontmatter YAML: {exc}") from exc
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# Date resolution
# ---------------------------------------------------------------------------

_FILENAME_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")


def _resolve_note_date(path: Path, frontmatter: dict[str, object]) -> date | None:
    """Resolve a note's date: filename ``YYYY-MM-DD.md`` first, then a
    ``date:`` frontmatter key as fallback. Returns ``None`` if neither
    source yields a valid date (the caller skips such notes silently --
    real vaults accumulate templates and one-off notes in the Daily
    folder that shouldn't abort the whole scan)."""
    match = _FILENAME_DATE_RE.match(path.name)
    if match is not None:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass  # invalid calendar date in the filename -- fall through

    raw = frontmatter.get("date")
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, str):
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

_DRIVE_LETTER_RE = re.compile(r"^[A-Za-z]$")


def _parse_obsidian_arg(raw: str) -> tuple[str, list[str]]:
    """Split a ``dir:field1,field2,...`` CLI argument into directory and
    fields. Fields are mandatory -- unlike CSV's optional column suffix,
    there is no auto-expansion, so a missing or empty field list raises.

    There's no fixed extension to anchor on (``path`` is a directory, not
    a ``.csv`` file), so instead of CSV's ``.csv:`` boundary this splits
    on the *last* colon in the string, first excluding a colon at index 1
    that's a Windows drive letter (``C:\\vault\\Daily:mood`` must not
    split at the drive letter's colon).
    """
    colon_positions = [i for i, c in enumerate(raw) if c == ":"]
    if colon_positions and colon_positions[0] == 1 and _DRIVE_LETTER_RE.match(raw[:1]):
        colon_positions = colon_positions[1:]

    error = ValueError(
        "Obsidian directory argument must include fields, e.g. path:field1,field2."
    )
    if not colon_positions:
        raise error

    split_at = colon_positions[-1]
    directory, suffix = raw[:split_at], raw[split_at + 1 :]
    if not suffix or "/" in suffix or "\\" in suffix:
        raise error

    fields = [f.strip() for f in suffix.split(",") if f.strip()]
    if not fields:
        raise error

    return directory, fields


# ---------------------------------------------------------------------------
# Directory scanning
# ---------------------------------------------------------------------------


def _scan_notes(directory: str) -> list[tuple[date, dict[str, object]]]:
    """Scan *directory* (non-recursive, top-level ``.md`` files only) and
    return ``(date, frontmatter)`` pairs for every note whose date could
    be resolved, sorted by date.

    Multiple notes resolving to the same date keep only the first in
    sorted-filename order and skip the rest, matching the "don't crash on
    messy real-world data" posture used throughout this module.
    """
    p = Path(directory)
    if not p.exists():
        raise RuntimeError(f"Directory not found: {directory}")
    if not p.is_dir():
        raise RuntimeError(f"Not a directory: {directory}")

    seen_dates: set[date] = set()
    notes: list[tuple[date, dict[str, object]]] = []
    for note_path in sorted(p.glob("*.md")):
        text = note_path.read_text(encoding="utf-8")
        frontmatter = _extract_frontmatter(text, note_path)
        note_date = _resolve_note_date(note_path, frontmatter)
        if note_date is None or note_date in seen_dates:
            continue
        seen_dates.add(note_date)
        notes.append((note_date, frontmatter))

    if not notes:
        raise RuntimeError(f"{directory}: no daily notes with a resolvable date found.")

    notes.sort(key=lambda pair: pair[0])
    return notes


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------


def _extract_numeric_field(
    frontmatter: dict[str, object], field: str, *, path: str
) -> float | None:
    """Return ``frontmatter[field]`` coerced to ``float``.

    Returns ``None`` when *field* is absent, or present but empty (YAML
    ``null`` -- e.g. ``exercise: `` with nothing after the colon, the
    common habit-tracker-template pattern of a key that's always present
    but only filled in on days it applies). This mirrors CSV's blank-cell
    handling: a blank/empty value is a normal "no entry today", not an
    error. Raises when *field* is present with an actual non-numeric
    value (a string, list, bool, etc.), matching CSV's raise-on-a-
    present-but-invalid-cell behavior -- only a genuinely empty value is
    silently skipped, never a malformed one.
    """
    if field not in frontmatter:
        return None
    value = frontmatter[field]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(
            f"{path}: field {field!r} has a non-numeric value: {value!r}"
        )
    result = float(value)
    if math.isnan(result) or math.isinf(result):
        raise RuntimeError(
            f"{path}: field {field!r} has a non-numeric value: {value!r}"
        )
    return result


# ---------------------------------------------------------------------------
# Public fetch function
# ---------------------------------------------------------------------------


def fetch_obsidian_series(
    items: list[str], period: str, *, tz: str = "UTC"
) -> dict[str, TimeSeries]:
    """Load numeric YAML-frontmatter fields from Obsidian daily-notes
    vault directories and return labelled time-series data.

    Conforms to the ``fetch_fn`` signature used by the TUI and CLI.

    Each entry in *items* is ``directory:field1,field2,...`` (see
    :func:`_parse_obsidian_arg`); fields are mandatory. Each note's date
    is resolved from its filename (``YYYY-MM-DD.md``) or, failing that, a
    ``date:`` frontmatter key; notes with neither are skipped. Series are
    labelled ``<field>``, or ``<dirname>.<field>`` if the same field is
    requested from more than one directory. *tz* controls which timezone
    to-date periods (ytd/mtd/wtd/dtd/htd) anchor their calendar boundary
    in.
    """
    now = datetime.now(timezone.utc)
    resolved_tz = resolve_tz(tz)
    seen: set[str] = set()
    scan_cache: dict[str, list[tuple[date, dict[str, object]]]] = {}
    result: dict[str, TimeSeries] = {}

    for raw_arg in items:
        directory, fields = _parse_obsidian_arg(raw_arg)
        resolved_dir = str(Path(directory).expanduser().resolve())
        dedup_key = f"{resolved_dir}:{','.join(fields)}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        if resolved_dir not in scan_cache:
            scan_cache[resolved_dir] = _scan_notes(resolved_dir)
        notes = scan_cache[resolved_dir]

        for field in fields:
            series: TimeSeries = []
            for note_date, frontmatter in notes:
                value = _extract_numeric_field(
                    frontmatter, field, path=f"{resolved_dir}/{note_date}"
                )
                if value is not None:
                    dt = datetime.combine(note_date, time.min, tzinfo=timezone.utc)
                    series.append((dt, value))

            if not series:
                raise RuntimeError(f"{directory}:{field}: field not found in any note.")

            series = filter_period(series, period, reference=now, tz=resolved_tz)
            if not series:
                raise RuntimeError(
                    f"{directory}:{field}: no data left after trimming to "
                    f"period={period}."
                )

            label = field
            if label in result:
                label = f"{Path(directory).name}.{field}"
            result[label] = series

    return result
