"""Tests for termseries.period functions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from termseries.period import (
    _to_date_cutoff,
    filter_period,
    pad_datetime_str,
    parse_period,
    parse_time_bound,
    resolve_tz,
    xlim_now,
    yahoo_auto_interval,
    yahoo_covering_range,
)

# ===================================================================
# _to_date_cutoff
# ===================================================================


class TestToDateCutoff:
    """Test the _to_date_cutoff helper with a frozen 'now'."""

    # Wednesday 2024-07-17 14:35:22 UTC
    NOW = datetime(2024, 7, 17, 14, 35, 22, tzinfo=timezone.utc)

    def test_non_to_date_returns_none(self) -> None:
        assert _to_date_cutoff("7d", self.NOW) is None
        assert _to_date_cutoff("max", self.NOW) is None
        assert _to_date_cutoff("auto", self.NOW) is None

    def test_ytd(self) -> None:
        assert _to_date_cutoff("ytd", self.NOW) == datetime(
            2024, 1, 1, tzinfo=timezone.utc
        )

    def test_mtd(self) -> None:
        assert _to_date_cutoff("mtd", self.NOW) == datetime(
            2024, 7, 1, tzinfo=timezone.utc
        )

    def test_wtd(self) -> None:
        # 2024-07-17 is a Wednesday; Monday is 2024-07-15
        assert _to_date_cutoff("wtd", self.NOW) == datetime(
            2024, 7, 15, tzinfo=timezone.utc
        )

    def test_wtd_on_monday(self) -> None:
        monday = datetime(2024, 7, 15, 10, 0, 0, tzinfo=timezone.utc)
        assert _to_date_cutoff("wtd", monday) == datetime(
            2024, 7, 15, tzinfo=timezone.utc
        )

    def test_dtd(self) -> None:
        assert _to_date_cutoff("dtd", self.NOW) == datetime(
            2024, 7, 17, tzinfo=timezone.utc
        )

    def test_htd(self) -> None:
        assert _to_date_cutoff("htd", self.NOW) == datetime(
            2024, 7, 17, 14, 0, 0, tzinfo=timezone.utc
        )

    def test_defaults_to_utc_now(self) -> None:
        """Without an explicit now, should return a cutoff before utcnow."""
        cutoff = _to_date_cutoff("ytd")
        assert cutoff is not None
        assert cutoff <= datetime.now(timezone.utc)

    def test_dtd_honors_explicit_tz_across_a_utc_date_boundary(self) -> None:
        """A far-ahead-of-UTC zone (UTC+14) has already crossed into the next
        local day while UTC is still on the previous one -- dtd's cutoff must
        reflect the *local* midnight, not UTC midnight."""
        # 2024-07-17 23:30 UTC == 2024-07-18 13:30 in UTC+14
        now_utc = datetime(2024, 7, 17, 23, 30, tzinfo=timezone.utc)
        utc_plus_14 = timezone(timedelta(hours=14))
        cutoff = _to_date_cutoff("dtd", now_utc, tz=utc_plus_14)
        assert cutoff == datetime(2024, 7, 18, tzinfo=utc_plus_14)
        # The UTC-only cutoff would incorrectly still be 2024-07-17.
        assert _to_date_cutoff("dtd", now_utc) == datetime(
            2024, 7, 17, tzinfo=timezone.utc
        )

    def test_ytd_honors_explicit_tz_across_a_year_boundary(self) -> None:
        """A far-behind-UTC zone (UTC-12) is still in the previous local year
        while UTC has already crossed into the new one."""
        # 2025-01-01 05:00 UTC == 2024-12-31 17:00 in UTC-12
        now_utc = datetime(2025, 1, 1, 5, 0, tzinfo=timezone.utc)
        utc_minus_12 = timezone(timedelta(hours=-12))
        cutoff = _to_date_cutoff("ytd", now_utc, tz=utc_minus_12)
        assert cutoff == datetime(2024, 1, 1, tzinfo=utc_minus_12)
        # The UTC-only cutoff would incorrectly already be 2025.
        assert _to_date_cutoff("ytd", now_utc) == datetime(
            2025, 1, 1, tzinfo=timezone.utc
        )


class TestResolveTz:
    def test_utc(self) -> None:
        assert resolve_tz("UTC") is timezone.utc

    def test_local_is_none(self) -> None:
        assert resolve_tz("local") is None

    def test_iana_name(self) -> None:
        tz = resolve_tz("America/Los_Angeles")
        assert tz is not None
        assert str(tz) == "America/Los_Angeles"


# ===================================================================
# pad_datetime_str
# ===================================================================


class TestPadDatetimeStr:
    def test_year_only(self) -> None:
        assert pad_datetime_str("2024") == "2024-01-01T00:00:00"

    def test_year_month(self) -> None:
        assert pad_datetime_str("2024-05") == "2024-05-01T00:00:00"

    def test_full_date(self) -> None:
        assert pad_datetime_str("2024-05-17") == "2024-05-17T00:00:00"

    def test_date_with_hour(self) -> None:
        assert pad_datetime_str("2024-05-17T12") == "2024-05-17T12:00:00"

    def test_date_with_hour_minute(self) -> None:
        assert pad_datetime_str("2024-05-17T12:30") == "2024-05-17T12:30:00"

    def test_full_datetime_unchanged(self) -> None:
        assert pad_datetime_str("2024-05-17T12:30:45") == "2024-05-17T12:30:45"

    def test_space_separator(self) -> None:
        assert pad_datetime_str("2024-05-17 12:30") == "2024-05-17T12:30:00"

    def test_preserves_z_suffix(self) -> None:
        assert pad_datetime_str("2024-05Z") == "2024-05-01T00:00:00Z"

    def test_preserves_offset_suffix(self) -> None:
        assert pad_datetime_str("2024-05+02:00") == "2024-05-01T00:00:00+02:00"


class TestPadDatetimeStrRoundUp:
    """round_up=True fills to the *end* of the given granularity, for use
    as a --to bound (e.g. --to 2026 should cover all of 2026)."""

    def test_year_only(self) -> None:
        assert pad_datetime_str("2024", round_up=True) == "2024-12-31T23:59:59"

    def test_year_month_uses_calendar_month_length(self) -> None:
        assert pad_datetime_str("2024-02", round_up=True) == "2024-02-29T23:59:59"
        assert pad_datetime_str("2023-02", round_up=True) == "2023-02-28T23:59:59"
        assert pad_datetime_str("2024-04", round_up=True) == "2024-04-30T23:59:59"

    def test_full_date_rounds_up_to_end_of_day(self) -> None:
        assert pad_datetime_str("2024-05-17", round_up=True) == "2024-05-17T23:59:59"

    def test_date_with_hour_rounds_up_remaining_time(self) -> None:
        assert pad_datetime_str("2024-05-17T12", round_up=True) == (
            "2024-05-17T12:59:59"
        )

    def test_date_with_hour_minute_rounds_up_seconds(self) -> None:
        assert pad_datetime_str("2024-05-17T12:30", round_up=True) == (
            "2024-05-17T12:30:59"
        )

    def test_full_datetime_unchanged(self) -> None:
        assert (
            pad_datetime_str("2024-05-17T12:30:45", round_up=True)
            == "2024-05-17T12:30:45"
        )

    def test_preserves_z_suffix(self) -> None:
        assert pad_datetime_str("2024Z", round_up=True) == "2024-12-31T23:59:59Z"


# ===================================================================
# parse_time_bound
# ===================================================================


class TestParseTimeBound:
    NOW = datetime(2024, 7, 17, 14, 35, 22, tzinfo=timezone.utc)

    def test_now_keyword(self) -> None:
        assert parse_time_bound("now", now=self.NOW, tz=timezone.utc) == self.NOW

    def test_relative_period(self) -> None:
        result = parse_time_bound("7d", now=self.NOW, tz=timezone.utc)
        assert result == self.NOW - timedelta(days=7)

    def test_rejects_max(self) -> None:
        with pytest.raises(ValueError, match="cannot be 'max' or 'auto'"):
            parse_time_bound("max", now=self.NOW, tz=timezone.utc)

    def test_partial_iso_date_is_padded(self) -> None:
        result = parse_time_bound("2024-05", now=self.NOW, tz=timezone.utc)
        assert result == datetime(2024, 5, 1, tzinfo=timezone.utc)

    def test_full_iso_datetime(self) -> None:
        result = parse_time_bound("2024-05-17T12:30:00Z", now=self.NOW, tz=timezone.utc)
        assert result == datetime(2024, 5, 17, 12, 30, tzinfo=timezone.utc)

    def test_naive_value_uses_given_tz(self) -> None:
        result = parse_time_bound("2024-05-17", now=self.NOW, tz=None)
        assert result == datetime(2024, 5, 17).astimezone(timezone.utc)

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError, match="ISO-8601"):
            parse_time_bound("not-a-date", now=self.NOW, tz=timezone.utc)

    def test_round_up_year_only_covers_end_of_year(self) -> None:
        """Regression test: `--to 2026` must cover all of 2026, not just its
        first instant, or a security that only trades in 2026 gets filtered
        out of a `--from 2025 --to 2026` window entirely."""
        result = parse_time_bound("2026", now=self.NOW, tz=timezone.utc, round_up=True)
        assert result == datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    def test_round_up_default_is_false(self) -> None:
        result = parse_time_bound("2026", now=self.NOW, tz=timezone.utc)
        assert result == datetime(2026, 1, 1, tzinfo=timezone.utc)


# ===================================================================
# parse_period
# ===================================================================


class TestParsePeriod:
    def test_days(self) -> None:
        assert parse_period("14d") == timedelta(days=14)

    def test_single_day(self) -> None:
        assert parse_period("1d") == timedelta(days=1)

    def test_weeks(self) -> None:
        assert parse_period("2w") == timedelta(weeks=2)

    def test_hours(self) -> None:
        assert parse_period("6h") == timedelta(hours=6)

    def test_minutes(self) -> None:
        assert parse_period("30m") == timedelta(minutes=30)

    def test_months(self) -> None:
        assert parse_period("3mo") == timedelta(days=90)

    def test_years(self) -> None:
        assert parse_period("1y") == timedelta(days=365)

    def test_max_returns_none(self) -> None:
        assert parse_period("max") is None

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid period"):
            parse_period("abc")

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid period"):
            parse_period("")

    def test_no_number_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid period"):
            parse_period("d")

    def test_no_unit_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid period"):
            parse_period("14")

    def test_unknown_unit_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid period"):
            parse_period("5x")

    @pytest.mark.parametrize("period", ["ytd", "mtd", "wtd", "dtd", "htd"])  # type: ignore[misc]
    def test_to_date_returns_positive_timedelta(self, period: str) -> None:
        result = parse_period(period)
        assert isinstance(result, timedelta)
        assert result > timedelta(0)


# ===================================================================
# yahoo_covering_range
# ===================================================================


class TestYahooCoveringRange:
    def test_native_1d(self) -> None:
        assert yahoo_covering_range("1d") == "1d"

    def test_native_5d(self) -> None:
        assert yahoo_covering_range("5d") == "5d"

    def test_3d_covers_to_5d(self) -> None:
        assert yahoo_covering_range("3d") == "5d"

    def test_14d_covers_to_1mo(self) -> None:
        assert yahoo_covering_range("14d") == "1mo"

    def test_7d_covers_to_1mo(self) -> None:
        # 7d = 7 days > 5d native, so needs 1mo
        assert yahoo_covering_range("7d") == "1mo"

    def test_2w_covers_to_1mo(self) -> None:
        assert yahoo_covering_range("2w") == "1mo"

    def test_2mo_covers_to_3mo(self) -> None:
        assert yahoo_covering_range("2mo") == "3mo"

    def test_1mo_exact(self) -> None:
        assert yahoo_covering_range("1mo") == "1mo"

    def test_6mo_exact(self) -> None:
        assert yahoo_covering_range("6mo") == "6mo"

    def test_1y_exact(self) -> None:
        assert yahoo_covering_range("1y") == "1y"

    def test_2y_exact(self) -> None:
        assert yahoo_covering_range("2y") == "2y"

    def test_3y_covers_to_5y(self) -> None:
        assert yahoo_covering_range("3y") == "5y"

    def test_max(self) -> None:
        assert yahoo_covering_range("max") == "max"

    def test_30m_covers_to_1d(self) -> None:
        assert yahoo_covering_range("30m") == "1d"

    def test_huge_period_covers_to_max(self) -> None:
        assert yahoo_covering_range("20y") == "max"

    @pytest.mark.parametrize("period", ["ytd", "mtd", "wtd", "dtd", "htd"])  # type: ignore[misc]
    def test_to_date_returns_valid_range(self, period: str) -> None:
        result = yahoo_covering_range(period)
        assert result in {
            "1d",
            "5d",
            "1mo",
            "3mo",
            "6mo",
            "1y",
            "2y",
            "5y",
            "10y",
            "max",
        }


# ===================================================================
# yahoo_auto_interval
# ===================================================================


class TestYahooAutoInterval:
    def test_1d_gets_5m(self) -> None:
        assert yahoo_auto_interval("1d") == "5m"

    def test_30m_gets_5m(self) -> None:
        assert yahoo_auto_interval("30m") == "5m"

    def test_5d_gets_15m(self) -> None:
        assert yahoo_auto_interval("5d") == "15m"

    def test_7d_gets_15m(self) -> None:
        assert yahoo_auto_interval("7d") == "15m"

    def test_1mo_gets_1d(self) -> None:
        assert yahoo_auto_interval("1mo") == "1d"

    def test_1y_gets_1d(self) -> None:
        assert yahoo_auto_interval("1y") == "1d"

    def test_max_gets_1d(self) -> None:
        assert yahoo_auto_interval("max") == "1d"

    @pytest.mark.parametrize("period", ["ytd", "mtd", "wtd", "dtd", "htd"])  # type: ignore[misc]
    def test_to_date_returns_valid_interval(self, period: str) -> None:
        result = yahoo_auto_interval(period)
        assert result in {"5m", "15m", "1d"}


# ===================================================================
# filter_period
# ===================================================================


class TestFilterPeriod:
    def _make_daily_series(self, n: int = 100) -> list[tuple[datetime, float]]:
        base = datetime(2024, 6, 1, tzinfo=timezone.utc)
        return [(base + timedelta(days=i), float(i)) for i in range(n)]

    def test_max_returns_unchanged(self) -> None:
        series = self._make_daily_series()
        assert filter_period(series, "max") == series

    def test_1d(self) -> None:
        series = self._make_daily_series()
        filtered = filter_period(series, "1d")
        assert len(filtered) == 2

    def test_7d(self) -> None:
        series = self._make_daily_series()
        filtered = filter_period(series, "7d")
        assert len(filtered) == 8

    def test_30d(self) -> None:
        series = self._make_daily_series()
        filtered = filter_period(series, "30d")
        assert len(filtered) == 31

    def test_14d(self) -> None:
        series = self._make_daily_series()
        filtered = filter_period(series, "14d")
        assert len(filtered) == 15

    def test_2w(self) -> None:
        series = self._make_daily_series()
        filtered = filter_period(series, "2w")
        assert len(filtered) == 15

    def test_empty_series(self) -> None:
        assert filter_period([], "7d") == []

    def test_ytd_uses_absolute_cutoff(self) -> None:
        """YTD should filter based on Jan 1st of current year, not relative."""
        now = datetime.now(timezone.utc)
        jan1 = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        # Create series spanning from last year to now
        series = [
            (jan1 - timedelta(days=10), 1.0),  # last year — excluded
            (jan1 - timedelta(days=1), 2.0),  # last year — excluded
            (jan1, 3.0),  # included
            (jan1 + timedelta(days=30), 4.0),  # included
        ]
        filtered = filter_period(series, "ytd")
        assert len(filtered) == 2
        assert filtered[0][2:] == ()  # just to confirm tuple structure
        assert filtered[0][0] == jan1

    def test_dtd_uses_absolute_cutoff(self) -> None:
        """DTD should filter based on start of today."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        series = [
            (today_start - timedelta(hours=2), 1.0),  # yesterday — excluded
            (today_start, 2.0),  # included
            (today_start + timedelta(hours=6), 3.0),  # included
        ]
        filtered = filter_period(series, "dtd")
        assert len(filtered) == 2

    def test_to_date_empty_series(self) -> None:
        assert filter_period([], "ytd") == []

    def test_ytd_honors_explicit_reference(self) -> None:
        """An explicit reference must anchor ytd/dtd/etc, not live datetime.now().

        Without this, multiple series filtered in the same call (each with an
        explicit shared reference) could get inconsistent cutoffs depending on
        exactly when each call happens to execute.
        """
        reference = datetime(2023, 6, 15, 12, 0, tzinfo=timezone.utc)
        jan1_2023 = datetime(2023, 1, 1, tzinfo=timezone.utc)
        series = [
            (datetime(2022, 12, 31, tzinfo=timezone.utc), 1.0),  # before ref's year
            (jan1_2023, 2.0),  # included
            (reference, 3.0),  # included
        ]
        filtered = filter_period(series, "ytd", reference=reference)
        assert filtered == [(jan1_2023, 2.0), (reference, 3.0)]

    def test_dtd_honors_explicit_reference(self) -> None:
        reference = datetime(2023, 6, 15, 18, 0, tzinfo=timezone.utc)
        today_start = datetime(2023, 6, 15, 0, 0, tzinfo=timezone.utc)
        series = [
            (datetime(2023, 6, 14, 23, 0, tzinfo=timezone.utc), 1.0),  # yesterday
            (today_start, 2.0),  # included
            (reference, 3.0),  # included
        ]
        filtered = filter_period(series, "dtd", reference=reference)
        assert filtered == [(today_start, 2.0), (reference, 3.0)]

    def test_dtd_honors_explicit_tz(self) -> None:
        """A UTC-12 user's 'today' includes a point plain UTC dtd would miss.

        reference = 2024-07-17 05:00 UTC = 2024-07-16 17:00 in UTC-12, so the
        user's local "today" is July 16. A point at 2024-07-16 18:00 UTC is
        also local July 16 (06:00), so it belongs in the local window -- but
        its UTC calendar date is July 16, before the UTC-only cutoff of
        2024-07-17 00:00 (start of reference's *UTC* day), so plain UTC dtd
        wrongly excludes it.
        """
        utc_minus_12 = timezone(timedelta(hours=-12))
        reference = datetime(2024, 7, 17, 5, 0, tzinfo=timezone.utc)
        point_local_today_utc_yesterday = datetime(
            2024, 7, 16, 18, 0, tzinfo=timezone.utc
        )
        series = [
            (point_local_today_utc_yesterday, 1.0),
            (reference, 2.0),
        ]
        utc_only = filter_period(series, "dtd", reference=reference)
        assert utc_only == [(reference, 2.0)]  # UTC dtd excludes the July-16 point

        tz_aware = filter_period(series, "dtd", reference=reference, tz=utc_minus_12)
        assert tz_aware == series  # both points fall on local July 16 in UTC-12


# ===================================================================
# xlim_now
# ===================================================================


class TestXlimNow:
    _DATA: dict[str, list[tuple[datetime, float]]] = {
        "A": [
            (datetime(2024, 1, 1, tzinfo=timezone.utc), 10.0),
            (datetime(2024, 6, 1, tzinfo=timezone.utc), 20.0),
        ]
    }

    def test_auto_returns_none(self) -> None:
        assert xlim_now("auto", self._DATA) is None

    def test_relative_period_returns_tuple(self) -> None:
        result = xlim_now("7d", self._DATA)
        assert result is not None
        start, end = result
        assert (end - start).days == 7

    def test_to_date_period_returns_tuple(self) -> None:
        """'ytd' should return a (Jan 1, now) window."""
        result = xlim_now("ytd", self._DATA)
        assert result is not None
        start, end = result
        assert start.month == 1 and start.day == 1

    def test_max_uses_earliest_data_point(self) -> None:
        result = xlim_now("max", self._DATA)
        assert result is not None
        start, _end = result
        assert start == datetime(2024, 1, 1, tzinfo=timezone.utc)

    def test_max_empty_data_returns_none(self) -> None:
        assert xlim_now("max", {}) is None
