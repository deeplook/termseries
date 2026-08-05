# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- TUI Period menu: "from-to…" option opens a modal to pick an explicit date range, matching the CLI's `--from`/`--to`; partial dates (e.g. `2024-05`) are zero-padded to a full timestamp

### Fixed
- `--from`/`--to` (CLI and TUI) now pad partial dates direction-aware: `--from` rounds down to the start of the given granularity, `--to` rounds up to its end (calendar-aware month lengths). Previously both rounded down, so e.g. `--from 2025 --to 2026` resolved to `2026-01-01T00:00:00` as the end bound and silently dropped any data that only existed within 2026

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
