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
