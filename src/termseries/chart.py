"""Backend-independent numerical chart transformations."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

_Transform = Callable[[Sequence[Any], Sequence[float]], tuple[list[Any], list[float]]]


def _transform_indexed(
    xs: Sequence[Any], ys: Sequence[float]
) -> tuple[list[Any], list[float]]:
    if not ys:
        return list(xs), list(ys)
    base = ys[0]
    if base == 0 or math.isnan(base):
        # No meaningful "% of start" when the baseline is 0 or missing.
        return list(xs), [float("nan")] * len(ys)
    return list(xs), [100.0 * y / base for y in ys]


def _transform_drawdown(
    xs: Sequence[Any], ys: Sequence[float]
) -> tuple[list[Any], list[float]]:
    if not ys:
        return list(xs), list(ys)
    peak: float | None = None
    dd: list[float] = []
    for y in ys:
        if math.isnan(y):
            dd.append(float("nan"))
        else:
            peak = y if peak is None else max(peak, y)
            dd.append(float("nan") if peak == 0 else (y / peak - 1.0) * 100.0)
    return list(xs), dd


def _transform_returns(
    xs: Sequence[Any], ys: Sequence[float]
) -> tuple[list[Any], list[float]]:
    if len(ys) < 2:
        return list(xs), list(ys)
    returns: list[float] = []
    for i in range(1, len(ys)):
        prev = ys[i - 1]
        if prev == 0 or math.isnan(prev) or math.isnan(ys[i]):
            returns.append(float("nan"))
        else:
            returns.append((ys[i] / prev - 1.0) * 100.0)
    return list(xs[1:]), returns


def _transform_cumulative(
    xs: Sequence[Any], ys: Sequence[float]
) -> tuple[list[Any], list[float]]:
    if not ys:
        return list(xs), list(ys)
    cumulative: list[float] = []
    total = 0.0
    for y in ys:
        if math.isnan(y):
            cumulative.append(float("nan"))
        else:
            total += y
            cumulative.append(total)
    return list(xs), cumulative


def _transform_delta(
    xs: Sequence[Any], ys: Sequence[float]
) -> tuple[list[Any], list[float]]:
    if len(ys) < 2:
        return list(xs), list(ys)
    return list(xs[1:]), [ys[i] - ys[i - 1] for i in range(1, len(ys))]


_TRANSFORMS: dict[str, _Transform] = {
    "indexed": _transform_indexed,
    "drawdown": _transform_drawdown,
    "returns": _transform_returns,
    "cumulative": _transform_cumulative,
    "delta": _transform_delta,
}
