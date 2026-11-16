# Browser charts and Python usage

Install the optional dependencies before selecting the browser renderer:

```sh
pip install 'termseries[browser]'
```

Matplotlib remains the default renderer for PNG and terminal output. Plotly produces
interactive HTML snapshots with hover, zoom, pan, reset, and legend toggles. Fetching
requires whatever connection the source normally uses; the exported HTML works offline.
Changing the visible range does not fetch additional observations.

## Try the browser charts

These interactive examples reuse the indexed comparison, missing-observation gap,
and seasonal overlay from the [renderer gallery](gallery.md). Choose a tab, hover
for exact values, drag to zoom, or toggle a series in the legend. Reset view
restores the initial comparison. All observations are deterministic synthetic data.

<iframe src="../examples/browser-demos.html"
        title="Interactive indexed, gap and seasonal chart examples"
        loading="lazy"
        style="width:100%;height:650px;border:1px solid #dbe1e8;border-radius:8px;"></iframe>

[Open these examples in a separate page](examples/browser-demos.html), or see the
[full static-versus-interactive comparison](examples/browser-examples.html).

## Command line

Options shared by sources go before the source command:

```sh
# Standalone HTML: indexed TSLA and NVDA daily closing prices.
termseries --backend plotly --mode indexed --ratio 16:9 --theme light \
  --output stocks.html --open yahoo --last 1y TSLA NVDA

# Chart fragment for an existing HTML document.
termseries --backend plotly --html-fragment --mode indexed --ratio 16:9 \
  --theme light --output stocks-fragment.html yahoo --last 1y TSLA NVDA
```

`--output auto` creates an automatically named HTML file. `--output -` writes HTML
to stdout, with progress messages on stderr. Explicit paths must end in `.html` or
`.htm`. `--open` opens a saved file and cannot be combined with stdout output.

Browser output does not support `--interactive` (the terminal UI), `--reload`,
`--copy`, Matplotlib `--style` files, inline output, or terminal protocols. Use
`--protocol auto` to override a terminal protocol inherited from configuration.

## Python: render your own observations

`termseries.browser.render_html` returns a string. It does not fetch data, write
files, or open a browser. Its input is a dictionary mapping each series name to a
chronologically sorted list of `(timezone-aware datetime, float)` observations.
Prefer UTC timestamps internally; `tz` controls display and calendar alignment.

This example runs without network access:

```python
from datetime import datetime, timezone
from pathlib import Path

from termseries.browser import render_html

series = {
    "Temperature": [
        (datetime(2026, 1, 1, hour, tzinfo=timezone.utc), value)
        for hour, value in enumerate([20.1, 20.5, 21.2, 20.8])
    ]
}

html = render_html(
    series,
    ratio=(16, 9),
    period_label="Four hourly observations",
    title="Room temperature",
    value_unit="°C",
    theme="light",
    tz="Europe/Berlin",
)
Path("temperature.html").write_text(html, encoding="utf-8")
```

The first three arguments are `series`, `ratio`, and `period_label`; each may also
be passed by keyword. The default result is a complete HTML document. Use
`html_fragment=True` to return a chart `<div>` and its executable scripts without
document-level wrappers.

## Python: TSLA and NVDA indexed to 100

Fetch observations separately, then pass them to the renderer. This example creates
a report with an embedded chart:

```python
from pathlib import Path

from termseries.browser import render_html
from termseries.yahoo import fetch_yahoo_series

series = fetch_yahoo_series(["TSLA", "NVDA"], period="1y", interval="1d")

fragment = render_html(
    series,
    ratio=(16, 9),
    period_label="1 year",
    mode="indexed",
    html_fragment=True,
    title="TSLA vs NVDA — indexed to 100",
    tz="America/New_York",
    theme="light",
)

page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TSLA vs NVDA</title>
</head>
<body>
  <h1>TSLA vs NVDA</h1>
  <section style="max-width:1000px">{fragment}</section>
</body>
</html>
"""
Path("tsla-nvda-indexed.html").write_text(page, encoding="utf-8")
```

Each series starts at 100 using its own first returned observation. A value of 120
means a 20% gain from that baseline. The renderer does not automatically align the
first observation across series; choose a common starting date when that matters.
For TSLA alone in absolute prices, fetch `["TSLA"]`, use `mode="absolute"`, and set
`value_unit="USD"` and a suitable title.

## Rendering options

Arguments and keyword options for `render_html`:

| Option | Meaning |
| --- | --- |
| `html_fragment=False` | Full HTML document by default; `True` returns embeddable markup and scripts |
| `ratio` (required) | `(width, height)` aspect-ratio tuple; passed as the second argument or by keyword |
| `fit=False` | `True` sizes the chart to 90% of the viewport height |
| `mode="absolute"` | `absolute`, `indexed`, `log`, `drawdown`, `returns`, `relative`, `cumulative`, `delta`, or `seasonal` |
| `theme="auto"` | `light`, `dark`, or the browser's color preference when loaded |
| `tz="UTC"` | `UTC`, `local`, or an IANA zone such as `America/New_York` |
| `value_unit="USD"` | Unit label for values; percentage modes and relative mode supply their own unit |
| `interval_label="Daily"` | Sampling description used for returns/delta titles |
| `title=None` | Custom title; otherwise generated from mode and period |
| `show_legend=True` | Whether to show the legend |
| `line_style="linear"` | `linear`, `step-pre`, `step-post`, or `step-mid` |
| `color_cycle="tab10"` | `tab10`, `Set1`, `Set2`, `Dark2`, `Accent`, `Pastel1`, or `tab20` |
| `xlim=None` | Optional `(start_datetime, end_datetime)` initial time bounds |
| `cycle=None`, `cycle_count=None` | Axis metadata for already prepared seasonal overlays |

`ratio` is an explicit function argument, not an option with a default. Values in
the table describe the other defaults. `--ratio fit` on the CLI maps to `fit=True`.

Width is responsive. A fragment's height follows its containing element's width
according to `ratio`, with a minimum of 240 pixels. Full-page output uses viewport
width for the ratio, a 320-pixel minimum, and an 85%-of-viewport-height preferred
cap. `fit=True` takes precedence. Exact pixel dimensions, arbitrary background
colors, and transparency are not exposed by `render_html` or the CLI; use the
light/dark themes for supported backgrounds.

With `tz="local"`, the generating machine's IANA zone is stored in the chart so
viewing it elsewhere does not change its interpretation. Tick labels adapt to
zoom and available width. Full hover timestamps retain the timezone and offset.

## Data preparation: gaps and seasonal cycles

The CLI prepares observations before rendering. Direct Python callers must do the
same preparation when needed; `render_html` does not accept a `gaps` option.

For missing timestamps, call `termseries.gaps.apply_gaps(series, "show")` before
rendering. It returns series with NaN sentinels that break lines. `"connect"` skips
detection. A duration such as `"1h"` additionally requires the interval to exceed
that duration, while retaining the normal cadence-based detection rule.

Gap detection requires at least three observations. It detects intervals exceeding
1.5 times the median positive interval; duplicates do not contribute to that
median. Both comparisons are strict. Missing mathematical results remain gaps even
with `"connect"`. No policy fills with zero or removes time from the axis.

For seasonal mode, use `termseries.seasonal.count_cycles` and `wrap_series` on the
prepared input before rendering. Supply the same display timezone (resolved with
`termseries.period.resolve_tz`) to both helpers, then pass the wrapped data with
`mode="seasonal"`, `cycle="year"` (or `"quarter"` / a duration), and `cycle_count`.
Do not pass unwrapped observations and expect the renderer to split them into cycles.
Seasonal hover shows projected cycle positions rather than original timestamps.

Numerical transformations for indexed, drawdown, returns, cumulative and delta
modes run inside the renderer; do not pre-transform the data a second time. Relative
mode uses the last observation per display-timezone calendar date, joined on common
dates, rather than an intraday timestamp join. Existing gap insertion precedes value
transformations, so a sentinel can also suppress adjacent returns/deltas.

## Embedding and sharing

Insert a fragment into the page body through a rendered HTML template or server-side
include. Each fragment has a unique chart ID. Its scripts must execute: assigning
the string to `innerHTML` alone does not initialize the chart. A template engine
must treat this generated markup as HTML rather than escaping the entire fragment.

Fragments include Plotly.js and the observations. Multiple fragments currently
repeat the library payload. The comparison gallery demonstrates loading it once
when building a page directly from figures; that is separate from the fragment CLI.

A full-page export can instead be embedded using an iframe:

```html
<iframe src="stocks.html" title="TSLA vs NVDA"
        style="width:100%;height:450px;border:0"></iframe>
```

Serve the chart file at a path the host page can access. An iframe keeps the chart's
styles and scripts separate. Neither method publishes the chart or starts a server.

See the [offline comparison gallery](examples/browser-examples.html) for actual
Matplotlib PNGs beside interactive Plotly charts, and the
[validation report](validation.md) for measured performance and
compatibility checks. Large datasets can produce files tens of megabytes in size;
there is no application-level downsampling or point cap.
