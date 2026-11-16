# Matplotlib styles

Chart appearance is controlled by Matplotlib `.mplstyle` files. termseries
ships with two built-in themes (`dark` and `light`) that are automatically
selected based on your terminal's background color. You can override any
setting by passing an extra style file with `--style`:

```bash
# Use thinner lines, no markers
termseries --style my-overrides.mplstyle yahoo TSLA AAPL
```

The override file only needs the keys you want to change -- everything else is
inherited from the base theme.

### Built-in theme defaults

Both `dark.mplstyle` and `light.mplstyle` share the same layout settings
(they differ only in colors):

| Key | Default | Controls |
|---|---|---|
| `axes.titlesize` | 14 | Chart title |
| `axes.labelsize` | 12 | Axis labels ("Date (UTC)", "Close (USD)") |
| `xtick.labelsize` | 10 | X-axis tick values |
| `ytick.labelsize` | 10 | Y-axis tick values |
| `legend.fontsize` | 10 | Legend text |
| `lines.linewidth` | 2 | Line thickness |
| `lines.marker` | o | Data-point marker shape |
| `lines.markersize` | 6 | Marker size |
| `grid.alpha` | 0.3 | Grid transparency |
| `grid.linewidth` | 0.5 | Grid line thickness |
| `figure.dpi` | 200 | Output resolution |

### Example override file

```ini
# my-overrides.mplstyle
axes.titlesize:   18          # bigger title
axes.labelsize:   16          # bigger axis labels
xtick.labelsize:  14          # bigger tick labels
ytick.labelsize:  14
lines.linewidth:  1.5
lines.marker:     None        # no markers, just lines
figure.dpi:       150         # lower DPI for smaller file size
grid.linestyle:   --          # dashed grid
```

See the full
[Matplotlib customization guide](https://matplotlib.org/stable/users/explain/customizing.html)
for all available keys.

These `.mplstyle` overrides apply to Matplotlib only. For supported browser theme
and size settings, see [Browser charts](browser.md#rendering-options).
