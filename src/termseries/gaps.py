"""Gap detection and NaN insertion for time series data."""

from __future__ import annotations

from datetime import timedelta
from statistics import median

from termseries.types import TimeSeries


def insert_gaps(
    series: TimeSeries,
    threshold: float = 1.5,
    max_gap: timedelta | None = None,
) -> TimeSeries:
    """Detect temporal gaps and insert NaN sentinels to break plot lines.

    Parameters
    ----------
    series : TimeSeries
        Sorted list of ``(datetime, float)`` pairs.
    threshold : float
        Multiplier applied to the median interval.  Intervals exceeding
        ``threshold * median_interval`` are classified as gaps.
    max_gap : timedelta | None
        If given, only gaps **exceeding** this duration receive a NaN
        sentinel.  Gaps at or below *max_gap* are left connected.

    Returns
    -------
    TimeSeries
        A new list with ``(midpoint, NaN)`` sentinels inserted at each gap.
    """
    if len(series) < 3:
        return list(series)

    intervals = [
        (series[i + 1][0] - series[i][0]).total_seconds()
        for i in range(len(series) - 1)
    ]
    med = median(intervals)
    if med <= 0:
        return list(series)

    gap_threshold_secs = threshold * med

    result: TimeSeries = [series[0]]
    for i in range(1, len(series)):
        dt_prev, _ = series[i - 1]
        dt_cur, _ = series[i]
        interval_secs = (dt_cur - dt_prev).total_seconds()

        if interval_secs > gap_threshold_secs and (
            max_gap is None or (dt_cur - dt_prev) > max_gap
        ):
            midpoint = dt_prev + (dt_cur - dt_prev) / 2
            result.append((midpoint, float("nan")))

        result.append(series[i])

    return result
