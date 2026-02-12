"""Tests for termseries.period functions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from termseries.period import (
    filter_period,
    parse_period,
    yahoo_auto_interval,
    yahoo_covering_range,
)

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

    def test_ytd_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid period"):
            parse_period("ytd")


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
