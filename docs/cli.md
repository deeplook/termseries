# CLI reference


```sh
termseries [GLOBAL OPTIONS] SOURCE [SOURCE OPTIONS] [ITEMS...]
termseries --help
termseries yahoo --help
termseries csv --help
```

## Shared options

| Option | Description |
|---|---|
| `--backend` | `matplotlib` (default) for terminal/PNG, or optional `plotly` for browser HTML |
| `--html-fragment` | Export embeddable markup and scripts; requires `--backend plotly` |
| `--open` | Open the saved browser chart; requires file output and `--backend plotly` |
| `--ratio W:H` | Figure aspect ratio (default: 4:1); `fit` fills the terminal or uses viewport height for browser output |
| `--theme` | `light`, `dark`, or `auto` (terminal detection for PNG; browser preference for HTML) |
| `--output` | `auto`, `inline` (PNG only), `-` (stdout), or a file path |
| `--mode` | Chart mode: absolute, indexed, log, drawdown, returns, relative, cumulative, delta, seasonal |
| `--cycle` | Seasonal cycle length: `year`, `quarter`, or a duration (e.g. `1w`, `90d`) — only valid with `--mode seasonal`, defaults to `year` (see [Seasonal Mode](seasonal.md)) |
| `--title` | Custom chart title (default: auto-generated from mode/period/series) |
| `--legend` / `--no-legend` | Show or hide the series legend (default: shown) |
| `--tz TZ` | Timezone for x-axis: `UTC` (default), `local`, or IANA name (e.g. `Europe/Berlin`) |
| `--colors` | Matplotlib color cycle: tab10, Set1, Set2, Dark2, Accent, Pastel1, tab20 |
| `--gaps` | Gap handling: `connect` (default), `show` (break lines at gaps), or duration threshold (e.g. `1h`) |
| `--line-style` | Line connection style: linear (default), step-pre, step-post, step-mid |
| `--style PATH` | Extra `.mplstyle` file layered on top of the base theme (see [Custom Styles](styles.md)) |
| `-c` / `--copy` | Copy plot to system clipboard |
| `-i` / `--interactive` | Launch Textual TUI |
| `--reload N` | TUI auto-reload interval in seconds; `0` disables it |
| `--protocol` | PNG inline protocol: `auto`, `kitty`, `iterm2`, or `sixel` |
| `--version` | Print the installed version and exit |

Source references: [Yahoo](sources/yahoo.md), [Polymarket](sources/polymarket.md),
[CSV](sources/csv.md), [Home Assistant](sources/hass.md), and
[Obsidian](sources/obsidian.md). See [Time ranges](time-ranges.md) for the shared
range syntax, [Output](output.md) for dispatch, and [Browser charts](browser.md)
for backend-specific restrictions.
