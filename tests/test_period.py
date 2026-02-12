"""Tests for termseries.period functions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from termseries.period import (
    _to_date_cutoff,
    filter_period,
    parse_period,
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
