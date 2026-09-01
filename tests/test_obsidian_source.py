"""Tests for termseries.obsidian_source functions."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from termseries.obsidian_source import (
    _extract_frontmatter,
    _extract_numeric_field,
    _parse_obsidian_arg,
    _resolve_note_date,
    _scan_notes,
    fetch_obsidian_series,
)

# ===================================================================
# _extract_frontmatter
# ===================================================================


class TestExtractFrontmatter:
    def test_valid_block_parses(self) -> None:
        text = "---\nmood: 7\nweight: 72.5\n---\n\nBody text.\n"
        assert _extract_frontmatter(text, Path("note.md")) == {
            "mood": 7,
            "weight": 72.5,
        }

    def test_no_block_returns_empty(self) -> None:
        assert _extract_frontmatter("Just a plain note.\n", Path("note.md")) == {}

    def test_block_parses_to_non_dict_returns_empty(self) -> None:
        text = "---\n- a\n- b\n---\nBody\n"
        assert _extract_frontmatter(text, Path("note.md")) == {}

    def test_empty_block_returns_empty(self) -> None:
        text = "---\n---\nBody\n"
        assert _extract_frontmatter(text, Path("note.md")) == {}

    def test_malformed_yaml_raises(self) -> None:
        text = "---\nmood: [unclosed\n---\nBody\n"
        with pytest.raises(RuntimeError, match="invalid frontmatter YAML"):
            _extract_frontmatter(text, Path("note.md"))

    def test_block_not_at_start_returns_empty(self) -> None:
        text = "\n---\nmood: 7\n---\nBody\n"
        assert _extract_frontmatter(text, Path("note.md")) == {}

    def test_crlf_line_endings_handled(self) -> None:
        text = "---\r\nmood: 7\r\n---\r\nBody\r\n"
        assert _extract_frontmatter(text, Path("note.md")) == {"mood": 7}


# ===================================================================
# _resolve_note_date
# ===================================================================


class TestResolveNoteDate:
    def test_filename_match(self) -> None:
        assert _resolve_note_date(Path("2024-05-01.md"), {}) == date(2024, 5, 1)

    def test_non_matching_filename_native_date_fallback(self) -> None:
        fm = {"date": date(2024, 5, 1)}
        assert _resolve_note_date(Path("random-note.md"), fm) == date(2024, 5, 1)

    def test_non_matching_filename_string_date_fallback(self) -> None:
        fm = {"date": "2024-05-01"}
        assert _resolve_note_date(Path("random-note.md"), fm) == date(2024, 5, 1)

    def test_non_matching_filename_no_date_key_returns_none(self) -> None:
        assert _resolve_note_date(Path("random-note.md"), {}) is None

    def test_invalid_calendar_date_in_filename_falls_back(self) -> None:
        fm = {"date": "2024-05-01"}
        assert _resolve_note_date(Path("2024-13-40.md"), fm) == date(2024, 5, 1)

    def test_invalid_calendar_date_in_filename_no_fallback_returns_none(self) -> None:
        assert _resolve_note_date(Path("2024-13-40.md"), {}) is None

    def test_date_key_wrong_type_returns_none(self) -> None:
        assert _resolve_note_date(Path("random-note.md"), {"date": 42}) is None
        assert _resolve_note_date(Path("random-note.md"), {"date": ["x"]}) is None

    def test_datetime_date_key_takes_date_part(self) -> None:
        fm = {"date": datetime(2024, 5, 1, 12, 30)}
        assert _resolve_note_date(Path("random-note.md"), fm) == date(2024, 5, 1)


# ===================================================================
# _parse_obsidian_arg
# ===================================================================


class TestParseObsidianArg:
    def test_single_field(self) -> None:
        assert _parse_obsidian_arg("Daily:mood") == ("Daily", ["mood"])

    def test_multiple_fields(self) -> None:
        assert _parse_obsidian_arg("Daily:mood,weight") == (
            "Daily",
            ["mood", "weight"],
        )

    def test_strips_whitespace(self) -> None:
        assert _parse_obsidian_arg("Daily: mood , weight ") == (
            "Daily",
            ["mood", "weight"],
        )

    def test_missing_colon_raises(self) -> None:
        with pytest.raises(ValueError, match="must include fields"):
            _parse_obsidian_arg("Daily")

    def test_trailing_comma_only_raises(self) -> None:
        with pytest.raises(ValueError, match="must include fields"):
            _parse_obsidian_arg("Daily:,")

    def test_empty_suffix_raises(self) -> None:
        with pytest.raises(ValueError, match="must include fields"):
            _parse_obsidian_arg("Daily:")

    def test_windows_drive_letter_with_fields(self) -> None:
        assert _parse_obsidian_arg("C:\\vault\\Daily:mood,weight") == (
            "C:\\vault\\Daily",
            ["mood", "weight"],
        )

    def test_windows_drive_letter_without_fields_raises(self) -> None:
        with pytest.raises(ValueError, match="must include fields"):
            _parse_obsidian_arg("C:\\vault\\Daily")

    def test_field_name_with_colon_documents_mangled_split(self) -> None:
        # A colon typo in the field list still splits at the *last* colon,
        # so the path absorbs the extra segment rather than crashing here.
        assert _parse_obsidian_arg("Daily:mood:weight") == (
            "Daily:mood",
            ["weight"],
        )


# ===================================================================
# _scan_notes
# ===================================================================


class TestScanNotes:
    def test_directory_not_found_raises(self) -> None:
        with pytest.raises(RuntimeError, match="Directory not found"):
            _scan_notes("/nonexistent/vault/Daily")

    def test_path_is_a_file_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "not-a-dir.md"
        f.write_text("---\nmood: 7\n---\n")
        with pytest.raises(RuntimeError, match="Not a directory"):
            _scan_notes(str(f))

    def test_empty_directory_raises(self, tmp_path: Path) -> None:
        with pytest.raises(RuntimeError, match="no daily notes"):
            _scan_notes(str(tmp_path))

    def test_no_resolvable_dates_raises(self, tmp_path: Path) -> None:
        (tmp_path / "Untitled.md").write_text("---\nmood: 7\n---\n")
        with pytest.raises(RuntimeError, match="no daily notes"):
            _scan_notes(str(tmp_path))

    def test_mixed_valid_invalid_notes_sorted(self, tmp_path: Path) -> None:
        (tmp_path / "2024-01-03.md").write_text("---\nmood: 3\n---\n")
        (tmp_path / "2024-01-01.md").write_text("---\nmood: 1\n---\n")
        (tmp_path / "Untitled.md").write_text("Just some scratch notes.\n")
        (tmp_path / "2024-01-02.md").write_text("---\nmood: 2\n---\n")
        notes = _scan_notes(str(tmp_path))
        assert [d for d, _ in notes] == [
            date(2024, 1, 1),
            date(2024, 1, 2),
            date(2024, 1, 3),
        ]

    def test_date_collision_first_wins(self, tmp_path: Path) -> None:
        # "2024-01-01 copy.md" sorts before "2024-01-01.md" (space < '.' in
        # ASCII), so it's the one processed first and kept.
        (tmp_path / "2024-01-01 copy.md").write_text(
            "---\ndate: 2024-01-01\nmood: 9\n---\n"
        )
        (tmp_path / "2024-01-01.md").write_text("---\nmood: 1\n---\n")
        notes = _scan_notes(str(tmp_path))
        assert len(notes) == 1
        assert notes[0][1]["mood"] == 9

    def test_subdirectories_not_recursed(self, tmp_path: Path) -> None:
        (tmp_path / "2024-01-01.md").write_text("---\nmood: 1\n---\n")
        sub = tmp_path / "Archive"
        sub.mkdir()
        (sub / "2024-01-02.md").write_text("---\nmood: 2\n---\n")
        notes = _scan_notes(str(tmp_path))
        assert len(notes) == 1
        assert notes[0][0] == date(2024, 1, 1)


# ===================================================================
# _extract_numeric_field
# ===================================================================


class TestExtractNumericField:
    def test_int_coerced_to_float(self) -> None:
        assert _extract_numeric_field({"mood": 7}, "mood", path="n") == 7.0

    def test_float_passed_through(self) -> None:
        assert _extract_numeric_field({"weight": 72.5}, "weight", path="n") == 72.5

    def test_absent_returns_none(self) -> None:
        assert _extract_numeric_field({}, "mood", path="n") is None

    def test_non_numeric_string_raises(self) -> None:
        with pytest.raises(RuntimeError, match="non-numeric value"):
            _extract_numeric_field({"mood": "great"}, "mood", path="n")

    def test_bool_raises(self) -> None:
        with pytest.raises(RuntimeError, match="non-numeric value"):
            _extract_numeric_field({"done": True}, "done", path="n")

    def test_none_value_skipped_like_absent(self) -> None:
        """A key present but left empty (YAML null, e.g. `exercise: ` with
        nothing after the colon) is the common habit-tracker-template
        pattern of a key that's always present but only filled in on days
        it applies -- treat it the same as absent, not an error."""
        assert _extract_numeric_field({"mood": None}, "mood", path="n") is None

    def test_nan_raises(self) -> None:
        with pytest.raises(RuntimeError, match="non-numeric value"):
            _extract_numeric_field({"mood": float("nan")}, "mood", path="n")


# ===================================================================
# fetch_obsidian_series
# ===================================================================


def _write_note(directory: Path, name: str, frontmatter_lines: list[str]) -> None:
    content = "---\n" + "\n".join(frontmatter_lines) + "\n---\n"
    (directory / name).write_text(content)


class TestFetchObsidianSeries:
    def test_single_dir_single_field(self, tmp_path: Path) -> None:
        _write_note(tmp_path, "2024-01-01.md", ["mood: 6"])
        _write_note(tmp_path, "2024-01-02.md", ["mood: 8"])
        result = fetch_obsidian_series([f"{tmp_path}:mood"], "max")
        assert list(result) == ["mood"]
        assert [v for _, v in result["mood"]] == [6.0, 8.0]

    def test_single_dir_multiple_fields(self, tmp_path: Path) -> None:
        _write_note(tmp_path, "2024-01-01.md", ["mood: 6", "weight: 74.2"])
        result = fetch_obsidian_series([f"{tmp_path}:mood,weight"], "max")
        assert set(result) == {"mood", "weight"}
        assert result["weight"][0][1] == 74.2

    def test_multiple_dirs_same_field_disambiguated(self, tmp_path: Path) -> None:
        dir_a = tmp_path / "Daily"
        dir_b = tmp_path / "Archive"
        dir_a.mkdir()
        dir_b.mkdir()
        _write_note(dir_a, "2024-01-01.md", ["mood: 6"])
        _write_note(dir_b, "2024-01-01.md", ["mood: 9"])
        result = fetch_obsidian_series([f"{dir_a}:mood", f"{dir_b}:mood"], "max")
        assert set(result) == {"mood", "Archive.mood"}
        assert result["mood"][0][1] == 6.0
        assert result["Archive.mood"][0][1] == 9.0

    def test_dedup_by_dir_and_field_set(self, tmp_path: Path) -> None:
        _write_note(tmp_path, "2024-01-01.md", ["mood: 6"])
        result = fetch_obsidian_series([f"{tmp_path}:mood", f"{tmp_path}:mood"], "max")
        assert list(result) == ["mood"]

    def test_same_dir_different_field_subsets_not_deduped(self, tmp_path: Path) -> None:
        _write_note(tmp_path, "2024-01-01.md", ["mood: 6", "weight: 74.2"])
        result = fetch_obsidian_series(
            [f"{tmp_path}:mood", f"{tmp_path}:weight"], "max"
        )
        assert set(result) == {"mood", "weight"}

    def test_field_absent_from_all_notes_raises(self, tmp_path: Path) -> None:
        _write_note(tmp_path, "2024-01-01.md", ["mood: 6"])
        with pytest.raises(RuntimeError, match="field not found in any note"):
            fetch_obsidian_series([f"{tmp_path}:nonexistent"], "max")

    def test_field_absent_from_some_notes_skips_silently(self, tmp_path: Path) -> None:
        _write_note(tmp_path, "2024-01-01.md", ["mood: 6"])
        _write_note(tmp_path, "2024-01-02.md", ["weight: 74.2"])
        result = fetch_obsidian_series([f"{tmp_path}:mood"], "max")
        assert len(result["mood"]) == 1

    def test_field_present_but_empty_skipped_silently(self, tmp_path: Path) -> None:
        """Regression test: a habit-tracker key present but left blank on
        days it doesn't apply (e.g. `exercise-dumbbells:` with nothing
        after the colon, parsing to YAML null) must be skipped like a
        blank CSV cell, not raise."""
        _write_note(tmp_path, "2024-01-01.md", ["exercise-dumbbells: 20"])
        _write_note(tmp_path, "2024-01-02.md", ["exercise-dumbbells:"])
        _write_note(tmp_path, "2024-01-03.md", ["exercise-dumbbells: 15"])
        result = fetch_obsidian_series([f"{tmp_path}:exercise-dumbbells"], "max")
        assert [v for _, v in result["exercise-dumbbells"]] == [20.0, 15.0]

    def test_period_filtering_applied(self, tmp_path: Path) -> None:
        now = datetime.now(timezone.utc)
        old_date = (now - timedelta(days=400)).strftime("%Y-%m-%d")
        recent_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        _write_note(tmp_path, f"{old_date}.md", ["mood: 3"])
        _write_note(tmp_path, f"{recent_date}.md", ["mood: 8"])
        result = fetch_obsidian_series([f"{tmp_path}:mood"], "7d")
        assert [v for _, v in result["mood"]] == [8.0]

    def test_period_trims_to_nothing_raises(self, tmp_path: Path) -> None:
        now = datetime.now(timezone.utc)
        old_date = (now - timedelta(days=400)).strftime("%Y-%m-%d")
        _write_note(tmp_path, f"{old_date}.md", ["mood: 3"])
        with pytest.raises(RuntimeError, match="no data left after trimming"):
            fetch_obsidian_series([f"{tmp_path}:mood"], "7d")

    def test_tz_is_resolved_and_threaded_to_filter_period(self, tmp_path: Path) -> None:
        _write_note(tmp_path, "2024-01-01.md", ["mood: 6"])
        with patch(
            "termseries.obsidian_source.filter_period",
            wraps=lambda pts, *a, **kw: pts,
        ) as mock_filter:
            fetch_obsidian_series([f"{tmp_path}:mood"], "ytd", tz="America/Los_Angeles")
        assert str(mock_filter.call_args.kwargs["tz"]) == "America/Los_Angeles"

    def test_tilde_in_path_is_expanded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        vault = tmp_path / "Daily"
        vault.mkdir()
        _write_note(vault, "2024-01-01.md", ["mood: 6"])
        result = fetch_obsidian_series(["~/Daily:mood"], "max")
        assert list(result) == ["mood"]

    def test_non_numeric_value_on_one_note_raises(self, tmp_path: Path) -> None:
        _write_note(tmp_path, "2024-01-01.md", ["mood: 6"])
        _write_note(tmp_path, "2024-01-02.md", ['mood: "great"'])
        with pytest.raises(RuntimeError, match="non-numeric value"):
            fetch_obsidian_series([f"{tmp_path}:mood"], "max")

    def test_directory_not_found_raises(self) -> None:
        with pytest.raises(RuntimeError, match="Directory not found"):
            fetch_obsidian_series(["/nonexistent/vault/Daily:mood"], "max")
