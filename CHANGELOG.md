# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-08-06

### Added
- `--mode seasonal` wraps a multi-cycle series into overlaid per-cycle lines (e.g. one line per year), with `--cycle year|quarter|<duration>` (default `year`) controlling the cycle length. Quarters and week-length (`1w`/`7d`) cycles are calendar-aligned (Monday-start for weeks); the x-axis label, tick format, and whether the timezone is shown all adapt to the chosen cycle. Works with `--interactive` (`-i`) too
- `--title` sets a custom chart title, overriding the auto-generated one
- `--legend`/`--no-legend` toggles the series legend (default: shown)
- X-axis tick labels are only rotated when they'd actually overlap horizontally at the rendered figure size, instead of always rotating
- TUI Period menu: "from-to…" option opens a modal to pick an explicit date range, matching the CLI's `--from`/`--to`; partial dates (e.g. `2024-05`) are zero-padded to a full timestamp
- Launching with `-i` and `--from`/`--to` now seeds that range as a pre-selected Period entry in the TUI instead of being rejected

### Fixed
- `--from`/`--to` (CLI and TUI) now pad partial dates direction-aware: `--from` rounds down to the start of the given granularity, `--to` rounds up to its end (calendar-aware month lengths). Previously both rounded down, so e.g. `--from 2025 --to 2026` resolved to `2026-01-01T00:00:00` as the end bound and silently dropped any data that only existed within 2026
- Yahoo: `--from`/`--to` windows reaching up to "now" (CLI and TUI) now request a properly sized native range instead of always `range=max`. Yahoo silently coarsens `interval=1d` data to monthly/quarterly bars when `range=max` is requested for a long-lived ticker (e.g. `--from 2026` on TSLA/AAPL returned ~1 point/month instead of daily data), even though the actual requested window was narrow
- An omitted `--to` no longer freezes the range end to the CLI's invocation time; it now stays open-ended ("up to now"), which matters for the TUI's live re-fetching -- a frozen end quickly looked "in the past" relative to a freshly recomputed "now", silently falling back to fetching `range=max` (and its known interval-coarsening) instead of a properly sized window
- `hass` charts now anchor the x-axis to "now" for `--last max` (like `csv` already did), so a sensor that stopped reporting shows up as a visible trailing gap instead of the chart silently rescaling to hide it. Previously only `csv` honored `max` vs `auto`; `hass` treated them identically
- `--gaps` is now honored in interactive mode (`-i`/`--interactive`); previously it only applied to the non-interactive one-shot render

## [0.2.0] - 2026-08-04

### Added
- Windows support: CI now runs the test suite on `windows-latest`

### Fixed
- Terminal capability detection no longer crashes on Windows, where `termios`/`tty` don't exist
- Force matplotlib's headless `Agg` backend so rendering doesn't probe for a missing Tk install
- Auto-generated output filenames sanitize characters (e.g. `:`) that Windows rejects in paths
- `fitbit-to-csv` now closes its sqlite3 connection explicitly, fixing temp-directory cleanup on Windows

## [0.1.0] - 2026-08-04

### Added
- Initial release
- Data sources: Yahoo Finance, Home Assistant, and local CSV files
- Chart modes: absolute, indexed, log, drawdown, returns, relative, cumulative, delta
- Terminal inline image rendering: Kitty, iTerm2, Sixel, with PNG file fallback
- Interactive Textual TUI with live input, auto-reload, and clipboard copy
- Configurable aspect ratio, color cycles, and custom `.mplstyle` themes
- Dark/light terminal theme detection
- CI, PyPI Trusted Publishing with attestations, and Docker support
