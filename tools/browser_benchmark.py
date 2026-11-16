"""Generate deterministic offline fixtures for browser performance checks.

Run: uv run --extra browser python tools/browser_benchmark.py /tmp/termseries-bench
Open each HTML in a browser and measure load and zoom separately from generation.
"""

from __future__ import annotations

import json
import math
import platform
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter

import plotly

from termseries.browser import render_html


def main() -> None:
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Warm the renderer before measuring fixture generation.
    render_html({"warmup": [(start, 1.0)]}, (2, 1), "benchmark")
    records = []
    for points, traces in ((1000, 1), (10000, 1), (100000, 1), (100000, 4)):
        data = {
            f"Series {trace + 1}": [
                (
                    start + timedelta(minutes=i),
                    100 + trace * 10 + math.sin(i / 11) + (i % 17) / 25,
                )
                for i in range(points)
            ]
            for trace in range(traces)
        }
        started = perf_counter()
        html = render_html(
            data,
            (2, 1),
            "benchmark",
            theme="light",
            title=f"{points:,} points × {traces} traces",
            value_unit="value",
        )
        elapsed = perf_counter() - started
        # Observe first painted chart in the browser without tool round-trip time.
        html = html.replace(
            "</body>",
            "<script>requestAnimationFrame(() => requestAnimationFrame(() => {"
            "window.__benchmarkReady = performance.now();"
            "}));</script></body>",
        )
        name = f"{points}-{traces}.html"
        path = output / name
        path.write_text(html, encoding="utf-8")
        records.append(
            {
                "file": name,
                "points_per_trace": points,
                "traces": traces,
                "generation_seconds": round(elapsed, 3),
                "bytes": path.stat().st_size,
            }
        )
    report = {
        "python": platform.python_version(),
        "plotly": plotly.__version__,
        "platform": platform.platform(),
        "cases": records,
    }
    (output / "generation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
