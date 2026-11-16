"""Build the offline Matplotlib/Plotly comparison gallery.

Run from the repository root: uv run --extra browser python tools/browser_examples.py
"""

# Embedded HTML/CSS and explanatory text intentionally keep readable lines.
# ruff: noqa: E501

import base64
import json
from datetime import datetime, timedelta, timezone
from html import escape
from math import cos, sin
from pathlib import Path

from plotly.offline import get_plotlyjs

from termseries.browser import _TICKS, build_figure
from termseries.gaps import apply_gaps
from termseries.render import _render_png
from termseries.seasonal import count_cycles, wrap_series

UTC = timezone.utc
start = datetime(2026, 1, 1, tzinfo=UTC)
prices = {
    "North · demo": [
        (
            start + timedelta(days=i),
            100 + 0.22 * i + 6 * sin(i / 8) - 13 * sin(i / 24) ** 6,
        )
        for i in range(120)
    ],
    "South · demo": [
        (
            start + timedelta(days=i),
            180 + 0.29 * i + 8 * cos(i / 12) - 18 * sin(i / 27) ** 6,
        )
        for i in range(120)
    ],
}
sensor_start = datetime(2026, 10, 19, tzinfo=UTC)
sensors = {
    "Room temperature": [
        (
            sensor_start + timedelta(minutes=15 * i),
            21 + 1.4 * sin(i / 13) + 0.2 * cos(i / 3),
        )
        for i in range(192)
        if not 55 <= i <= 86
    ]
}
steps = {
    "Heating setpoint": [
        (sensor_start + timedelta(hours=i), float(v))
        for i, v in enumerate(
            [
                18,
                18,
                18,
                18,
                21,
                21,
                21,
                20,
                20,
                20,
                18,
                18,
                18,
                18,
                18,
                18,
                21,
                21,
                21,
                21,
                19,
                19,
                19,
                18,
            ]
        )
    ]
}
annual = {
    "Temperature": [
        (
            datetime(y, 1, 1, tzinfo=UTC) + timedelta(days=i),
            12
            + 10 * sin((i - 90) / 365 * 6.283)
            + 0.8 * sin(i / 10)
            + (y - 2023) * 0.45,
        )
        for y in [2023, 2024, 2025]
        for i in range(365)
    ]
}
seasonal = wrap_series(annual, "year", tz=UTC)
dst_start = datetime(2026, 10, 25, 0, tzinfo=UTC)
dst = {
    "Power demand": [
        (dst_start + timedelta(minutes=10 * i), 1.2 + 0.25 * sin(i / 3) + 0.015 * i)
        for i in range(25)
    ]
}
examples = [
    (
        "overview",
        "01",
        "Multiple series",
        "Explore a snapshot",
        "Hover for exact values. Drag to zoom, double-click to reset, and click legend entries to hide a series.",
        prices,
        {"value_unit": "USD"},
        "Default absolute values · two independently scaled series",
    ),
    (
        "indexed",
        "02",
        "Indexed comparison",
        "Start from the same baseline",
        "Each series starts at 100. Compare proportional change even when the original price levels differ.",
        prices,
        {"mode": "indexed"},
        "--mode indexed",
    ),
    (
        "drawdown",
        "03",
        "Drawdown",
        "Distance from the running peak",
        "Values show the percentage below the highest value seen so far. A new high returns the curve to zero.",
        prices,
        {"mode": "drawdown"},
        "--mode drawdown",
    ),
    (
        "returns",
        "04",
        "Returns",
        "Changes between observations",
        "Daily percentage returns emphasize variation between adjacent observations rather than the overall price level.",
        prices,
        {"mode": "returns", "interval_label": "Daily"},
        "--mode returns",
    ),
    (
        "connect",
        "05",
        "Gap policy · connect",
        "The missing interval is bridged",
        "The sensor has an eight-hour outage. The default policy connects the observations on either side; elapsed time stays on the axis.",
        apply_gaps(sensors, "connect"),
        {"value_unit": "°C"},
        "--gaps connect",
    ),
    (
        "gaps",
        "06",
        "Gap policy · show",
        "The missing interval stays blank",
        "The same observations, with a midpoint missing-value sentinel. No interpolation or zero fill is introduced.",
        apply_gaps(sensors, "show"),
        {"value_unit": "°C"},
        "--gaps show",
    ),
    (
        "steps",
        "07",
        "Step lines",
        "A value holds until the next change",
        "A thermostat setpoint uses step-post: each recorded value stays constant until the next observation.",
        steps,
        {"value_unit": "°C", "line_style": "step-post"},
        "--line-style step-post",
    ),
    (
        "seasonal",
        "08",
        "Seasonal overlay",
        "Three years on one calendar",
        "Annual cycles overlap in a shared reference year. Hover shows cycle position, while legend entries identify the original year.",
        seasonal,
        {
            "mode": "seasonal",
            "cycle": "year",
            "cycle_count": count_cycles(annual, "year", tz=UTC),
            "value_unit": "°C",
        },
        "--mode seasonal --cycle year",
    ),
    (
        "timezone",
        "09",
        "Timezone · DST",
        "The same hour happens twice",
        "Europe/Berlin falls back on 25 October 2026. Hover distinguishes the repeated 02:00 hour using CEST +0200 and CET +0100.",
        dst,
        {"tz": "Europe/Berlin", "value_unit": "kW"},
        "--tz Europe/Berlin",
    ),
]

parts = []
for key, num, kicker, title, desc, data, options, flag in examples:
    # Identical prepared observations, display options and requested x bounds.
    times = [dt for points in data.values() for dt, _ in points]
    bounds = (min(times), max(times))
    common = dict(theme="light", title="", xlim=bounds, **options)
    png = _render_png(
        data,
        (2, 1),
        "synthetic example",
        figsize=(10, 6),
        save_dpi=160,
        **common,
    )
    encoded = base64.b64encode(png).decode("ascii")
    fig = build_figure(data, (2, 1), "synthetic example", **common)
    fig.update_layout(
        height=410,
        margin={"l": 60, "r": 35, "t": 40, "b": 65},
        legend={"orientation": "h", "y": 1.13, "x": 0},
        font={"family": "system-ui, sans-serif", "size": 11},
    )
    fig.update_xaxes(automargin=True, tickangle=0)
    fragment = fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        div_id="chart-" + key,
        config={"responsive": True, "displaylogo": False},
        post_script=_TICKS,
    )
    # Reset restores the original Plotly ranges without changing the static PNG.
    reset_range = [
        dt.astimezone(UTC).isoformat().replace("+00:00", "") for dt in bounds
    ]

    reset = escape(json.dumps(reset_range), quote=True)
    parts.append(f'''
<article id="{key}" class="example">
  <div class="card-head"><span class="number">{num}</span>
    <span class="kicker">{escape(kicker)}</span></div>
  <h2>{escape(title)}</h2><p class="description">{escape(desc)}</p>
  <div class="comparison">
    <section class="pane" aria-label="Matplotlib static chart">
      <div class="pane-heading"><strong>Matplotlib</strong><span>Static PNG</span></div>
      <div class="image-wrap"><img src="data:image/png;base64,{encoded}"
        width="1600" height="960" alt="Matplotlib: {escape(title)}"></div>
    </section>
    <section class="pane" aria-label="Plotly interactive chart">
      <div class="pane-heading"><strong>Plotly</strong><span>Interactive HTML</span>
        <button type="button" data-chart="chart-{key}" data-range="{reset}">
          Reset view</button></div>
      <div class="chart">{fragment}</div>
    </section>
  </div>
  <div class="flag">{escape(flag)}<span>{sum(map(len, data.values())):,} prepared points
    · identical observations, timezone, gap policy and initial time bounds</span></div>
</article>''')

css = """
:root{color-scheme:light;--ink:#111;--muted:#5b626b;--line:#dbe1e8;
--blue:#1f77b4;--ground:#f5f7fa}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;
background:var(--ground);color:var(--ink);font:15px/1.55 system-ui,sans-serif}
main{max-width:1500px;margin:auto;padding:48px 30px 64px}
header{border-top:4px solid var(--ink);padding-top:24px;margin-bottom:28px}
.eyebrow{font:12px ui-monospace,monospace;text-transform:uppercase;
letter-spacing:.13em;color:var(--blue)}h1{font-size:clamp(32px,5vw,60px);
letter-spacing:-.05em;line-height:1.06;margin:16px 0}
header p{max-width:850px;font-size:18px;color:var(--muted)}
.badges{display:flex;gap:8px;flex-wrap:wrap}.badges span{font-size:12px;
border:1px solid var(--line);padding:5px 10px;border-radius:20px;background:white}
nav{display:flex;gap:8px;flex-wrap:wrap;margin:26px 0}nav a{color:var(--ink);
background:white;border:1px solid var(--line);text-decoration:none;padding:7px 12px;
border-radius:6px;font-size:13px}nav a:hover,nav a:focus{border-color:var(--blue);
color:var(--blue)}.grid{display:grid;grid-template-columns:minmax(0,1fr);gap:24px}
.example{min-width:0;background:white;border:1px solid var(--line);border-radius:10px;
padding:24px 20px 16px;scroll-margin-top:20px;overflow:hidden}
.card-head{display:flex;align-items:center;gap:10px}.number{font:12px ui-monospace,
monospace;color:var(--blue);border:1px solid #b9d5eb;border-radius:4px;padding:2px 6px}
.kicker{text-transform:uppercase;font-size:11px;letter-spacing:.1em;color:var(--muted)}
h2{font-size:24px;letter-spacing:-.025em;line-height:1.2;margin:16px 0 10px}
.description{max-width:950px;color:var(--muted);margin:0 0 22px}
.comparison{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}
.pane{min-width:0;border:1px solid var(--line);border-radius:7px;overflow:hidden}
.pane-heading{display:flex;align-items:center;gap:10px;min-height:47px;padding:8px 14px;
border-bottom:1px solid var(--line);font-size:13px;flex-wrap:wrap}
.pane-heading span{color:var(--muted);font-size:12px}.pane-heading button{margin-left:auto;
border:1px solid var(--line);border-radius:4px;background:white;color:var(--blue);
font:inherit;font-size:12px;padding:4px 9px;cursor:pointer}
button:hover,button:focus-visible{border-color:var(--blue)}
.chart{min-width:0;width:100%;height:410px}.chart>div{min-width:0!important;max-width:100%}
.image-wrap{height:410px;display:flex;align-items:center;justify-content:center;
padding:8px;background:white}.image-wrap img{display:block;max-width:100%;
max-height:100%;width:auto;height:auto;object-fit:contain}
.flag{display:flex;gap:12px;justify-content:space-between;flex-wrap:wrap;
font:12px ui-monospace,monospace;color:var(--blue);margin-top:16px;
border-top:1px solid var(--line);padding-top:12px;overflow-wrap:anywhere}
.flag span{color:var(--muted);font:12px/1.5 system-ui,sans-serif}
footer{margin-top:32px;color:var(--muted);font-size:13px;border-top:1px solid var(--line);
padding-top:20px}footer p{max-width:980px}a{color:var(--blue)}
@media(max-width:850px){main{padding:28px 12px}.comparison{grid-template-columns:minmax(0,1fr)}
.example{padding:20px 10px 12px}.image-wrap{height:auto;min-height:220px}
.image-wrap img{width:100%;height:auto}h2{font-size:22px}header p{font-size:16px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
"""
nav = "".join(
    f'<a href="#{k}">{escape(label)}</a>'
    for k, label in [
        ("overview", "Overview"),
        ("indexed", "Indexed"),
        ("drawdown", "Drawdown"),
        ("returns", "Returns"),
        ("connect", "Connected gaps"),
        ("gaps", "Visible gaps"),
        ("steps", "Steps"),
        ("seasonal", "Seasonal"),
        ("timezone", "Timezone"),
    ]
)
html = (
    """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>termseries · Static vs interactive</title><style>"""
    + css
    + """</style><script>"""
    + get_plotlyjs()
    + """</script>
</head><body><main><header><div class="eyebrow">termseries / renderer comparison</div>
<h1>Same data. Two renderers.</h1>
<p>Compare the existing Matplotlib output with the optional Plotly backend.
Each pair uses exactly the same synthetic observations, transformation, gap policy,
timezone and initial time bounds.</p>
<div class="badges"><span>Nine direct comparisons</span><span>Real Matplotlib PNGs</span>
<span>Interactive Plotly charts</span><span>Works offline</span></div></header>
<nav aria-label="Examples">"""
    + nav
    + """</nav><div class="grid">"""
    + "".join(parts)
    + """</div>
<footer><p>The left panels are actual output from termseries’ Matplotlib renderer,
embedded as PNGs. The right panels use its Plotly figure builder. Tick placement,
legend layout, marker sizing and axis wording are renderer-specific, so differences
remain visible. Plotly adds hover, zoom, pan and legend controls; Reset view restores
the original comparison bounds and visible traces.</p>
<p>All values are deterministic demonstration data. No source fetching or live updates
occur in this page. Images and Plotly.js are embedded; no network connection or server
is needed. Styling follows termseries’ light theme and existing chart palette.</p>
</footer></main><script>
document.querySelectorAll('button[data-chart]').forEach(button => {
  button.addEventListener('click', async () => {
    const chart = document.getElementById(button.dataset.chart);
    await Plotly.restyle(chart, {visible:true});
    await Plotly.relayout(chart, {'xaxis.range':JSON.parse(button.dataset.range),
      'yaxis.autorange':true});
  });
});
</script></body></html>"""
)
path = Path(__file__).resolve().parents[1] / "docs/_source/browser-examples.html"
path.parent.mkdir(parents=True, exist_ok=True)
# Plotly's embedded bundle contains trailing whitespace; normalize the artifact.
html = "\n".join(line.rstrip(" \t") for line in html.split("\n")).rstrip("\n") + "\n"
path.write_text(html, encoding="utf-8")
print(
    f"{path}: {len(examples)} chart pairs, {path.stat().st_size / 1024 / 1024:.2f} MiB"
)
