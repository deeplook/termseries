"""Shared type aliases and enums for termseries."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

TimeSeries = list[tuple[datetime, float]]


class Mode(str, Enum):
    absolute = "absolute"
    indexed = "indexed"
    log = "log"
    drawdown = "drawdown"
    returns = "returns"
    relative = "relative"


class ColorCycle(str, Enum):
    tab10 = "tab10"
    Set1 = "Set1"
    Set2 = "Set2"
    Dark2 = "Dark2"
    Accent = "Accent"
    Pastel1 = "Pastel1"
    tab20 = "tab20"


class YahooPeriod(str, Enum):
    d1 = "1d"
    d5 = "5d"
    d7 = "7d"
    mo1 = "1mo"
    mo3 = "3mo"
    mo6 = "6mo"
    y1 = "1y"
    y2 = "2y"
    y5 = "5y"
    y10 = "10y"
    ytd = "ytd"
    max = "max"


class YahooInterval(str, Enum):
    auto = "auto"
    m1 = "1m"
    m5 = "5m"
    m15 = "15m"
    m30 = "30m"
    m60 = "60m"
    m90 = "90m"
    d1 = "1d"


class LineStyle(str, Enum):
    linear = "linear"
    step_pre = "step-pre"
    step_post = "step-post"
    step_mid = "step-mid"


class LastPeriod(str, Enum):
    all = "all"
    h1 = "1h"
    h3 = "3h"
    h6 = "6h"
    h12 = "12h"
    d1 = "1d"
    d2 = "2d"
    d7 = "7d"
    d30 = "30d"
    d90 = "90d"
    y1 = "1y"
