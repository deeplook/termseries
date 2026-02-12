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
