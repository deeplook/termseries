# Browser backend validation

Validated on 2026-11-16 on `feat/browser-backend`.

## Tests and compatibility

- Clean export of exactly the staged files, with no unrelated local experiments: 689 tests passed on Python 3.12.16 + Plotly 6.9.0, 3 Docker tests deselected, 86.36% coverage.

- Python 3.12.16 + Plotly 6.9.0: 698 workspace tests passed, 3 Docker tests deselected; 86.34% Python coverage (required minimum: 80%).
- Python 3.10.17 + Plotly 6.0.0: the same 698 workspace tests passed. This run exposed the existing `parse_time_bound` failure for a trailing `Z` on Python 3.10; normalizing to `+00:00` fixes the already-covered case.
- Ruff lint, formatting and strict mypy checks pass.
- CI now checks Plotly 6.0 explicitly on Python 3.10, in addition to its existing all-extras matrix and the new base-install checks.
- Actual built wheels were installed in isolated Python 3.10 environments, both without Plotly and with the browser extra plus Plotly 6.0.0. The smoke check invokes the installed CLI against a temporary CSV, checks PNG bytes, and checks either the missing-extra error or HTML stdout, as appropriate.
- Source and wheel distributions build successfully. `work/` artifacts are excluded from the source distribution; the browser renderer and extra dependency metadata are included in the wheel.

The workspace suite includes nine pre-existing untracked experiment tests. These are not part of this feature's commit. Docker execution and remote GitHub Actions are not claimed by these local checks.

## Real browser checks

Chrome 154 through Ego Lite, using local files. Verified with Plotly.py 6.9.0 and the Plotly.js 3.0.0 bundle supplied by Plotly.py 6.0.0:

- Explicit NaN/null gaps stay disconnected, including step-post lines.
- UTC geometry stays correct when the viewing browser uses another timezone.
- Europe/Berlin ticks and hover distinguish both occurrences of 02:00 at the autumn DST transition.
- Labels remain horizontal and compact, adapt after zoom and resize, and retain date/year/timezone context.
- Hover, legend hiding, zoom, reset and the comparison page's Reset view buttons work.
- The gallery loads all nine embedded Matplotlib PNGs and all nine Plotly charts, without horizontal page overflow at desktop or 390-pixel mobile widths.
- Offline loading succeeds with no external resource requests.

## Performance sample

Environment: Apple M4, 24 GB RAM, macOS 27.0.1, Chrome 154, Python 3.12.16, Plotly 6.9.0. Deterministic minute-resolution oscillating data; SVG `Scatter`, default line simplification, no application downsampling. All input observations remain in trace arrays. One figure per file.

| Points per trace | Traces | HTML generation | File size | Median chart ready | Median zoom |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000 | 1 | 0.029 s | 4.71 MiB | 162 ms | 67 ms |
| 10,000 | 1 | 0.112 s | 5.33 MiB | 165 ms | 67 ms |
| 100,000 | 1 | 0.950 s | 11.55 MiB | 295 ms | 67 ms |
| 100,000 | 4 | 3.709 s | 32.37 MiB | 664 ms | 67 ms |

Method: generation after a renderer warm-up; three browser navigations per fixture in one browser session. Chart-ready time is measured inside the page, from navigation time origin through two animation frames after the chart scripts, avoiding tool round-trip time. Browser zoom values combine five alternating range changes per navigation (15 samples), awaiting Plotly relayout and two animation frames. Those frame waits impose a measurement floor; the results are not raw renderer execution times or a measured frame-rate guarantee.

First navigation per fixture took 172, 526, 729 and 1,163 ms respectively; later trials benefit from browser/engine caches. Programmatic hover on the four-trace 100,000-point fixture completed in 24 ms including two animation frames and displayed the correct point's timestamp/value. Hover is one smoke measurement, not a distribution or pointer-movement benchmark.

These cases are usable on the tested desktop. Payload size is the clearest cost: four 100,000-point traces produce a 32 MiB file. This is not a validated maximum, and mobile performance, pathological data, many more traces, memory use and streaming are unmeasured. There is no silent point cap, downsampling, or automatic switch to WebGL.

To regenerate fixtures:

```sh
uv run --extra browser python tools/browser_benchmark.py /tmp/termseries-bench
```

The generator writes HTML and `generation.json` into the specified directory. Open fixtures in a browser, measure load separately from Python generation, and record hardware/browser details when comparing results.

## Remaining scope

Existing relative mode uses a display-timezone daily join. Existing sentinel insertion precedes value transforms, so gaps can affect adjacent returns/deltas. This feature preserves that processing order; redesigning gap metadata and relative alignment remains separate work. Live fetching, gap shading, trading calendars, WebGL selection and downsampling are not implemented.

## Embedding follow-up

`--html-fragment` adds direct insertion into host HTML. The follow-up workspace
suite passes 701 tests; its 121 browser/CLI tests also pass on Python 3.10 with
Plotly 6.0. Chrome checks with both tested Plotly versions confirm that two fragments
have independent IDs and zoom state, require no external resources, and resize
from a 480-pixel host to a 320-pixel host while preserving container-based sizing.
