"""Optional browser rendering contracts and CLI integration."""

from __future__ import annotations

import builtins
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from termseries.browser import build_figure, output_html, render_html, require_plotly
from termseries.cli import app
from termseries.gaps import apply_gaps

START = datetime(2026, 10, 25, tzinfo=timezone.utc)
DATA = {"Sensor": [(START + timedelta(hours=h), float(h + 1)) for h in (0, 1, 2, 8)]}


def test_missing_extra() -> None:
    original = builtins.__import__

    def without_plotly(name: str, *args: object, **kwargs: object) -> object:
        if name.startswith("plotly"):
            raise ImportError("not installed")
        return original(name, *args, **kwargs)  # type: ignore[arg-type]

    with patch("builtins.__import__", side_effect=without_plotly):
        with pytest.raises(RuntimeError, match=r"termseries\[browser\]"):
            require_plotly()
        result = CliRunner().invoke(app, ["--backend", "plotly", "yahoo", "FAKE"])
        assert result.exit_code != 0
        assert "browser" in result.output


@pytest.mark.parametrize("gaps,missing", [("connect", 0), ("show", 1), ("7h", 0)])
def test_gap_policy(gaps: str, missing: int) -> None:
    pytest.importorskip("plotly")
    fig = build_figure(apply_gaps(DATA, gaps), (4, 1), "1d")
    assert list(fig.data[0].y).count(None) == missing
    assert fig.data[0].connectgaps is False


@pytest.mark.parametrize(
    "mode", ["absolute", "indexed", "returns", "drawdown", "delta", "cumulative", "log"]
)
def test_modes(mode: str) -> None:
    pytest.importorskip("plotly")
    fig = build_figure(DATA, (4, 1), "1d", mode=mode)
    assert len(fig.data[0].y) == (3 if mode in ("returns", "delta") else 4)
    assert fig.layout.yaxis.type == ("log" if mode == "log" else "linear")


def test_missing_math_values_do_not_connect() -> None:
    pytest.importorskip("plotly")
    data = {
        "A": [
            (START, 1),
            (START + timedelta(hours=1), math.nan),
            (START + timedelta(hours=2), 3),
        ]
    }
    fig = build_figure(data, (4, 1), "1d")
    assert list(fig.data[0].y) == [1, None, 3]


def test_relative_date_join() -> None:
    pytest.importorskip("plotly")
    fig = build_figure(
        {"A": DATA["Sensor"], "B": DATA["Sensor"]}, (4, 1), "1d", mode="relative"
    )
    assert list(fig.data[0].y) == [1]


def test_html_is_self_contained_and_escapes_labels() -> None:
    pytest.importorskip("plotly")
    html = render_html(
        DATA,
        (4, 1),
        "1d",
        title="</script><script>alert(1)</script>",
        tz="Europe/Berlin",
    )
    assert "Plotly.newPlot" in html
    assert '<script src="' not in html
    assert "</script><script>alert(1)</script>" not in html
    assert (
        build_figure(DATA, (4, 1), "1d", tz="Europe/Berlin").layout.meta["timezone"]
        == "Europe/Berlin"
    )
    assert "plotly_relayout" in html


@pytest.mark.parametrize(
    "options",
    [
        ["--interactive"],
        ["--copy"],
        ["--output", "bad.png"],
        ["--output", "-", "--open"],
        ["--protocol", "kitty"],
    ],
)
def test_incompatible_options(options: list[str]) -> None:
    result = CliRunner().invoke(app, ["--backend", "plotly", *options, "yahoo", "FAKE"])
    assert result.exit_code != 0


def test_cli_html_stdout() -> None:
    pytest.importorskip("plotly")
    with patch("termseries.cli.fetch_yahoo_series", return_value=DATA):
        result = CliRunner().invoke(
            app, ["--backend", "plotly", "--output", "-", "yahoo", "FAKE"]
        )
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("<html>")
    assert "Fetching" not in result.stdout


def test_output_file_and_failed_open(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "chart.html"
    with patch("termseries.browser.webbrowser.open", return_value=False):
        output_html(
            "<html>test</html>",
            ["A"],
            (4, 1),
            "1d",
            output=str(path),
            open_browser=True,
        )
    assert path.read_text() == "<html>test</html>"
    assert "manually" in capsys.readouterr().err


def test_utc_geometry_and_requested_bounds() -> None:
    pytest.importorskip("plotly")
    end = START + timedelta(hours=8)
    fig = build_figure(DATA, (4, 1), "1d", tz="Europe/Berlin", xlim=(START, end))
    # Numeric dates are interpreted in the browser timezone by Plotly.js.
    # UTC strings keep geometry independent of the viewing machine's timezone.
    assert fig.data[0].x[0] == "2026-10-25T00:00:00"
    assert tuple(fig.layout.xaxis.range) == (
        "2026-10-25T00:00:00",
        "2026-10-25T08:00:00",
    )
    assert "CEST +0200" in fig.data[0].customdata[0]
    assert "CET +0100" in fig.data[0].customdata[1]


def test_local_zone_is_saved() -> None:
    pytest.importorskip("plotly")
    pytest.importorskip("tzlocal")
    with patch("tzlocal.get_localzone_name", return_value="Asia/Kolkata"):
        fig = build_figure(DATA, (4, 1), "1d", tz="local")
    assert fig.layout.meta["timezone"] == "Asia/Kolkata"
    assert "+0530" in fig.data[0].customdata[0]


def test_seasonal_axis_metadata() -> None:
    pytest.importorskip("plotly")
    from termseries.seasonal import wrap_series

    data = wrap_series(DATA, "7d", tz=timezone.utc)
    fig = build_figure(data, (4, 1), "1d", mode="seasonal", cycle="7d", cycle_count=1)
    assert fig.layout.meta["weekly"] is True
    assert "2000" not in fig.data[0].customdata[0]


@pytest.mark.parametrize(
    "style,shape",
    [
        ("linear", "linear"),
        ("step-pre", "vh"),
        ("step-post", "hv"),
        ("step-mid", "hvh"),
    ],
)
def test_step_shapes(style: str, shape: str) -> None:
    pytest.importorskip("plotly")
    fig = build_figure(apply_gaps(DATA, "show"), (4, 1), "1d", line_style=style)
    assert fig.data[0].line.shape == shape
    assert fig.data[0].y[-2] is None


@pytest.mark.parametrize(
    "width,start,end,zone,minimum",
    [
        (450, "2026-01-01", "2026-04-30", "UTC", 4),
        (230, "2026-01-01", "2026-04-30", "UTC", 4),
        (450, "2026-10-25 00:00", "2026-10-25 02:00", "Europe/Berlin", 4),
    ],
)
def test_adaptive_time_labels(
    width: int, start: str, end: str, zone: str, minimum: int
) -> None:
    """Execute the real tick script: compact, horizontal, responsive, DST-safe."""
    import json
    import shutil
    import subprocess

    from termseries.browser import _TICKS

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed to execute the browser tick formatter")
    fixture = {
        "layout": {"meta": {"timezone": zone}, "xaxis": {"title": {"text": "Time"}}},
        "_fullLayout": {"xaxis": {"range": [start, end], "_length": width}},
    }
    harness = (
        "const fixture = " + json.dumps(fixture) + ";\n"
        "fixture.on = () => {};\n"
        "global.document = {getElementById: () => fixture};\n"
        "global.ResizeObserver = class {observe() {}};\n"
        "global.Plotly = {relayout: (_, update) => {\n"
        " console.log(JSON.stringify(update)); return Promise.resolve(); }};\n"
    )
    result = subprocess.run(
        [node, "-e", harness + _TICKS], capture_output=True, text=True, check=True
    )
    update = json.loads(result.stdout)
    labels = update["xaxis.ticktext"]
    assert update["xaxis.tickangle"] == 0
    assert len(labels) >= minimum
    assert all(len(label.split("<br>")[0]) <= 8 for label in labels)
    if zone == "Europe/Berlin":
        assert any("GMT+2" in label for label in labels)
        assert any("GMT+1" in label for label in labels)
    else:
        assert all("2026" not in label and "GMT" not in label for label in labels)
