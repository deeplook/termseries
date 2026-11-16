"""Optional Plotly renderer and portable HTML output."""

from __future__ import annotations

import math
import sys
import webbrowser
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from termseries.chart import _TRANSFORMS
from termseries.period import resolve_tz
from termseries.seasonal import SECONDS_PER_WEEK, parse_cycle
from termseries.types import TimeSeries


def require_plotly() -> Any:
    """Import the optional dependency only when browser rendering is requested."""
    try:
        import plotly.graph_objects as go  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "Install the browser extra: pip install 'termseries[browser]'"
        ) from exc
    return go


def build_figure(
    series: dict[str, TimeSeries],
    ratio: tuple[int, int],
    period_label: str,
    *,
    mode: str = "absolute",
    color_cycle: str = "tab10",
    tz: str = "UTC",
    line_style: str = "linear",
    theme: str = "auto",
    value_unit: str = "USD",
    interval_label: str = "Daily",
    title: str | None = None,
    show_legend: bool = True,
    xlim: tuple[datetime, datetime] | None = None,
    cycle: str | None = None,
    cycle_count: int | None = None,
) -> Any:
    """Build a figure without network I/O; inputs already have gap/cycle processing."""
    go = require_plotly()
    if not series or not any(series.values()):
        raise ValueError("No data series provided.")
    if tz == "local":
        from tzlocal import get_localzone_name

        tz = get_localzone_name()
    target_tz = resolve_tz(tz)
    data = series
    if mode == "relative":
        if len(series) != 2:
            raise ValueError("Relative mode requires exactly 2 series.")
        a, b = series
        left = {dt.astimezone(target_tz).date(): v for dt, v in series[a]}
        right = {dt.astimezone(target_tz).date(): v for dt, v in series[b]}
        common = sorted(left.keys() & right.keys())
        if not common:
            raise RuntimeError(f"No overlapping dates for {a} and {b}.")
        data = {
            f"{a}/{b}": [
                (
                    datetime.combine(day, datetime.min.time(), target_tz),
                    left[day] / right[day] if right[day] != 0 else math.nan,
                )
                for day in common
            ]
        }
    # Reuse the project's existing categorical palettes exactly.
    from matplotlib import colormaps
    from matplotlib.colors import to_hex

    cmap = colormaps[color_cycle]
    colors = [to_hex(cmap(i)) for i in range(cmap.N)]
    fig = go.Figure()
    for index, (name, points) in enumerate(data.items()):
        xs = [dt for dt, _ in points]
        ys = [v for _, v in points]
        transform = _TRANSFORMS.get(mode)
        if transform:
            xs, ys = transform(xs, ys)
        hover = [
            escape(dt.astimezone(target_tz).strftime("%Y-%m-%d %H:%M:%S %Z %z"))
            for dt in xs
        ]
        if mode == "seasonal":
            hover = [
                escape(dt.astimezone(target_tz).strftime("%b %d %H:%M")) for dt in xs
            ]
        fig.add_trace(
            go.Scatter(
                x=[
                    dt.astimezone(timezone.utc).isoformat().replace("+00:00", "")
                    for dt in xs
                ],
                y=[
                    v if math.isfinite(v) and (mode != "log" or v > 0) else None
                    for v in ys
                ],
                name=escape(name),
                mode="lines+markers" if len(xs) <= 100 else "lines",
                connectgaps=False,
                line={
                    "shape": {
                        "linear": "linear",
                        "step-pre": "vh",
                        "step-post": "hv",
                        "step-mid": "hvh",
                    }[line_style],
                    "color": colors[index % len(colors)],
                },
                customdata=hover,
                hovertemplate="%{customdata}<br>%{y}<extra>%{fullData.name}</extra>",
            )
        )
    if not any(v is not None for trace in fig.data for v in trace.y):
        raise ValueError(
            "No finite values to plot (log mode requires positive values)."
        )
    unit = (
        "%"
        if mode in ("returns", "drawdown", "indexed")
        else "Ratio"
        if mode == "relative"
        else value_unit
    )
    label = f"{interval_label} {mode}" if mode in ("returns", "delta") else mode.title()
    xlabel = f"Time ({tz})"
    if mode == "seasonal":
        xlabel = f"Position within {cycle} ({cycle_count or 1} cycles)"
    cycle_spec = parse_cycle(cycle) if mode == "seasonal" and cycle else None
    fig.update_layout(
        title={
            "text": escape(title if title is not None else f"{label} ({period_label})")
        },
        template="plotly_dark" if theme == "dark" else "plotly_white",
        showlegend=show_legend,
        autosize=True,
        margin={"l": 65, "r": 25, "t": 65, "b": 65},
        xaxis={"type": "date", "title": xlabel},
        yaxis={"type": "log" if mode == "log" else "linear", "title": escape(unit)},
        meta={
            "timezone": tz,
            "seasonal": mode == "seasonal",
            "cycle": cycle,
            "weekly": cycle_spec is not None
            and cycle_spec.duration_seconds == SECONDS_PER_WEEK,
            "duration": cycle_spec is not None and cycle_spec.kind == "duration",
            "origin": datetime(2000, 1, 1, tzinfo=target_tz).timestamp() * 1000,
        },
    )
    if xlim:
        fig.update_xaxes(
            range=[
                dt.astimezone(timezone.utc).isoformat().replace("+00:00", "")
                for dt in xlim
            ]
        )
    return fig


# Date-axis tick strings are formatted explicitly: Plotly's native ticks do not
# provide an IANA timezone setting. Update after zoom/reset as well as initial load.
_TICKS = r"""
const chart = document.getElementById('{plot_id}');
const meta = chart.layout.meta;
const zone = meta.timezone;
const dateFormat = options => new Intl.DateTimeFormat('en-GB',
  {timeZone: zone, ...options});
const partsFormat = dateFormat({year:'numeric', month:'2-digit',
  day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit',
  hourCycle:'h23'});
const parts = value => Object.fromEntries(partsFormat.formatToParts(value)
  .filter(p => p.type !== 'literal').map(p => [p.type, Number(p.value)]));
const wallTime = value => {
  const p = parts(value);
  return Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
};
const instant = wall => {
  let value = wall;
  for (let i = 0; i < 4; i++) value += wall - wallTime(value);
  return value;
};
const millis = value => typeof value === 'number' ? value
  : Date.parse(value.replace(' ', 'T') + 'Z');
let busy = false;
let pending = false;
function ticks() {
  if (busy) { pending = true; return; }
  const axis = chart._fullLayout.xaxis;
  const [lo, hi] = axis.range.map(millis);
  const span = hi - lo;
  if (!Number.isFinite(span) || span <= 0) return;
  const count = Math.max(3, Math.min(14, Math.floor(axis._length / 78)));
  const day = 86400000;
  const target = span / count;
  const values = [];
  const steps = [1000, 5000, 15000, 30000, 60000, 300000, 900000,
    1800000, 3600000, 7200000, 10800000, 21600000, 43200000,
    day, 2*day, 7*day, 14*day];
  const step = steps.reduce((best, value) =>
    Math.abs(Math.log(value / target)) < Math.abs(Math.log(best / target))
      ? value : best);
  let calendar = false;
  if (target > 21*day
      || (meta.seasonal && meta.cycle === 'year' && span > 180*day)) {
    calendar = true;
    const months = Math.max(1, target / (30.44*day));
    const stride = months > 120 ? Math.ceil(months / 120)*120
      : [1, 2, 3, 6, 12, 24, 60, 120].reduce((best, value) =>
        Math.abs(Math.log(value / months)) < Math.abs(Math.log(best / months))
          ? value : best);
    const p = parts(lo);
    let month = Math.floor((p.year*12 + p.month - 1) / stride)*stride;
    for (let i = 0; i < 100; i++, month += stride) {
      const t = instant(Date.UTC(Math.floor(month / 12), month % 12, 1));
      if (t > hi) break;
      if (t >= lo) values.push(t);
    }
  } else if (step >= day) {
    let wall = Math.floor(wallTime(lo) / step)*step;
    for (let i = 0; i < 100; i++, wall += step) {
      const t = instant(wall);
      if (t > hi) break;
      if (t >= lo) values.push(t);
    }
  } else {
    const offset = wallTime(lo) - Math.floor(lo / 1000)*1000;
    const first = Math.ceil((lo + offset) / step)*step - offset;
    for (let t = first; t <= hi && values.length < 100; t += step) {
      values.push(t);
    }
  }
  let format;
  if (meta.weekly) {
    const days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
    format = {format: v => days[((Math.floor(
      (wallTime(v) - Date.UTC(2000,0,1)) / day) % 7) + 7) % 7]};
  } else if (meta.seasonal && meta.cycle !== 'year') {
    format = {format: v => 'Day ' +
      ((wallTime(v) - Date.UTC(2000,0,1)) / day + 1).toFixed(0)};
  } else if (calendar) {
    format = dateFormat(meta.seasonal ? {month:'short'}
      : span > 700*day ? {month:'short', year:'2-digit'} : {month:'short'});
  } else if (span <= 2*day) {
    format = dateFormat({hour:'2-digit', minute:'2-digit', hourCycle:'h23',
      ...(span < 120000 ? {second:'2-digit'} : {})});
  } else {
    format = dateFormat({day:'numeric', month:'short',
      ...(span > 700*day ? {year:'2-digit'} : {})});
  }
  let labels = values.map(v => format.format(v));
  // Distinguish repeated hours at DST without repeating offsets everywhere.
  if (!meta.seasonal && span <= 2*day) {
    labels = labels.map((label, i, all) => {
      if (all.indexOf(label) === all.lastIndexOf(label)) return label;
      const sameDay = values.filter((v, j) => all[j] === label)
        .every(v => parts(v).day === parts(values[i]).day);
      const context = dateFormat(sameDay ? {timeZoneName:'shortOffset'}
        : {day:'numeric', month:'short'});
      const suffix = sameDay ? context.formatToParts(values[i])
        .find(p => p.type === 'timeZoneName').value : context.format(values[i]);
      return label + '<br>' + suffix;
    });
  }
  const years = [parts(lo).year, parts(hi).year];
  const context = meta.seasonal ? chart.layout.xaxis.title.text
    : 'Time (' + zone + ') · ' + (years[0] === years[1]
      ? years[0] : years[0] + '–' + years[1]);
  busy = true;
  Plotly.relayout(chart, {'xaxis.tickmode':'array', 'xaxis.tickangle':0,
    'xaxis.tickvals':values.map(v => new Date(v).toISOString().slice(0, -1)),
    'xaxis.ticktext':labels, 'xaxis.title.text':context})
    .finally(() => {
      busy = false;
      if (pending) { pending = false; ticks(); }
    });
}
chart.on('plotly_relayout', e => {
  if (Object.keys(e).some(k => k.startsWith('xaxis.range')
      || k === 'xaxis.autorange' || k === 'autosize')) ticks();
});
new ResizeObserver(() => ticks()).observe(chart);
ticks();
"""


def render_html(
    series: dict[str, TimeSeries],
    ratio: tuple[int, int],
    period_label: str,
    **options: Any,
) -> str:
    """Serialize an offline document or an embeddable chart with Plotly.js."""
    html_fragment = options.pop("html_fragment", False)
    fit = options.pop("fit", False)
    fig = build_figure(series, ratio, period_label, **options)
    script = _TICKS
    if options.get("theme", "auto") == "auto":
        script += """
const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
if (dark) Plotly.relayout(chart, {paper_bgcolor: 'black',
  plot_bgcolor: 'black', 'font.color': 'white'});
"""
    height = (
        "90vh" if fit else f"max(320px, min(85vh, {100 * ratio[1] / ratio[0]:g}vw))"
    )
    if html_fragment and not fit:
        # Container-query units size the embedded chart relative to its host.
        height = f"max(240px, {100 * ratio[1] / ratio[0]:g}cqw)"
    html = str(
        fig.to_html(
            full_html=not html_fragment,
            include_plotlyjs=True,
            default_width="100%",
            default_height=height,
            config={"responsive": True, "displaylogo": False},
            post_script=script,
        )
    )

    if html_fragment:
        return (
            '<div style="container-type:inline-size;width:100%;min-width:0">'
            + html
            + "</div>"
        )
    return html


def output_html(
    html: str,
    names: list[str],
    ratio: tuple[int, int],
    period: str,
    *,
    output: str = "auto",
    open_browser: bool = False,
) -> None:
    """Write HTML to a file or stdout and optionally open the saved file."""
    if output == "-":
        sys.stdout.write(html)
        return
    from termseries.render import _auto_output_filename

    path = (
        Path(_auto_output_filename(names, period, ratio)).with_suffix(".html")
        if output == "auto"
        else Path(output)
    )
    try:
        path.write_text(html, encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Could not write to {path}: {exc}") from exc
    print(f"Wrote plot to {path}", file=sys.stderr)
    if open_browser:
        try:
            opened = webbrowser.open(path.resolve().as_uri())
        except webbrowser.Error:
            opened = False
        if not opened:
            print(
                f"Could not open browser; open {path.resolve()} manually.",
                file=sys.stderr,
            )
