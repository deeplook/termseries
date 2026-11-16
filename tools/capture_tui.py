"""Save a deterministic local TUI snapshot without fetching live data.

Run: env -u NO_COLOR uv run python tools/capture_tui.py

Textual exports terminal cells as SVG, while Ghostty/Kitty place the PNG chart
in a separate graphics layer. Reinsert that same PNG at the real widget bounds
so the exported snapshot contains both layers. No app widgets are restyled.
"""

from __future__ import annotations

import asyncio
import base64
import json
import math
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from PIL import Image
from textual.widgets import Select

from termseries.period import TUI_PERIOD_CHOICES
from termseries.tui import _build_app
from termseries.types import TimeSeries

COLUMNS, ROWS = 120, 38
SVG_NS = "http://www.w3.org/2000/svg"


def fetch_demo(names: list[str], period: str) -> dict[str, TimeSeries]:
    """Fixed demo curves, intentionally unrelated to actual stock history."""
    start = datetime(2025, 11, 17, tzinfo=timezone.utc)
    points = 252
    result = {}
    for index, name in enumerate(names):
        values = []
        for i in range(points):
            # Weekdays only, mirroring the shape of daily stock observations.
            day = start + timedelta(days=(i // 5) * 7 + i % 5)
            value = (
                100
                + index * 50
                + (0.16 + index * 0.16) * i
                + 10 * math.sin(i / 17 + index)
                - 18 * math.sin(i / 51) ** 6
            )
            values.append((day, value))
        result[name] = values
    return result


async def main() -> None:
    # Ghostty's real image widget retains PNG bytes without a lossy text fallback.
    with patch("termseries.tui._is_ghostty", return_value=True):
        app = _build_app(
            initial_columns=["TSLA", "NVDA"],
            period_choices=TUI_PERIOD_CHOICES,
            period="1y",
            mode="indexed",
            colors="tab10",
            theme="dark",
            tz="UTC",
            title="Indexed comparison · synthetic demo data",
            fetch_fn=fetch_demo,
        )
        async with app.run_test(size=(COLUMNS, ROWS)) as pilot:
            for _ in range(100):
                await pilot.pause()
                if app._last_png is not None:
                    break
            assert app._last_png is not None, "TUI did not finish rendering"
            # Exercise the public selection API after widgets mount, so each
            # current-value label has completed its reactive update as well.
            for select in app.query(Select):
                selected = select.value
                select.value = Select.BLANK
                await pilot.pause()
                select.value = selected
                await pilot.pause()
            await pilot.pause(0.2)
            chart = app.query_one("#chart")
            region = chart.region
            svg = app.export_screenshot(title="termseries · TUI · synthetic demo data")
            png = app._last_png
            selections = [str(widget.value) for widget in app.query("Select")]

    ET.register_namespace("", SVG_NS)
    root = ET.fromstring(svg)
    viewport = root.find(f".//{{{SVG_NS}}}clipPath[@id]/{{{SVG_NS}}}rect")
    assert viewport is not None
    cell_width = (float(viewport.attrib["width"]) + 1) / COLUMNS
    cell_height = (float(viewport.attrib["height"]) + 1) / ROWS
    layer = next(
        child
        for child in root
        if child.tag == f"{{{SVG_NS}}}g" and "clip-path" in child.attrib
    )
    image = ET.SubElement(
        layer,
        f"{{{SVG_NS}}}image",
        {
            "x": str(region.x * cell_width),
            "y": str(region.y * cell_height),
            "width": str(region.width * cell_width),
            "height": str(region.height * cell_height),
            "preserveAspectRatio": "none",
            "href": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
        },
    )
    assert image in layer
    svg = ET.tostring(root, encoding="unicode")
    # Use the local terminal font rather than requiring Rich's CDN font download.
    svg = re.sub(r"@font-face\s*\{[^}]+\}", "", svg)
    svg = svg.replace(
        "font-family: Fira Code, monospace;",
        'font-family: Menlo, "DejaVu Sans Mono", monospace;',
    )
    preview_dir = Path("work")
    preview_dir.mkdir(parents=True, exist_ok=True)
    path = preview_dir / "tui-preview.svg"
    path.write_text(svg + "\n", encoding="utf-8")
    metadata = {
        "data": "Deterministic synthetic observations; not historical stock prices",
        "terminal_columns": COLUMNS,
        "terminal_rows": ROWS,
        "selections": selections,
        "chart_region_cells": list(region),
        "chart_png_pixels": Image.open(BytesIO(png)).size,
        "svg_viewbox": root.attrib["viewBox"],
    }
    path.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(path)
    rasterizer = shutil.which("rsvg-convert")
    if rasterizer:
        png_path = path.with_suffix(".png")
        subprocess.run([rasterizer, "--output", str(png_path), str(path)], check=True)
        print(png_path)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
