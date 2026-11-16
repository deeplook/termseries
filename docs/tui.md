# Interactive terminal UI

Launch the Textual interface with `-i` or `--interactive`:

```sh
termseries -i yahoo TSLA NVDA
termseries -i csv readings.csv
termseries --mode seasonal --cycle 1w -i yahoo TSLA --last 6mo
termseries --reload 30 -i hass sensor.power_consumption --last 1d
```

The TUI uses Matplotlib PNGs. It has controls for source items, period, aspect
ratio, chart mode and color cycle. The period menu includes custom durations and
fixed from/to bounds. Initial `--from`/`--to` values seed a selected range.

Source inputs accept quoted items containing spaces. Chart resizing is debounced
and uses cached observations. Reloading fetches new observations; `--reload N`
sets an interval in seconds. The seasonal cycle is set at launch with `--cycle`,
not changed through a cycle dropdown.

| Key | Action |
| --- | --- |
| `?` or `Ctrl+H` | Help |
| `Left` / `Right` | Move between controls |
| `Ctrl+Y` | Copy current PNG to the clipboard |
| `Ctrl+R` | Toggle auto-reload |
| `Esc` or `Ctrl+D` | Quit |

The clipboard can be limited by SSH/container boundaries. Browser charts provide
client-side snapshot interaction instead; `--backend plotly` cannot be combined
with `--interactive` or `--reload`.
