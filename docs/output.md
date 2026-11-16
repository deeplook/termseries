# Output

## Matplotlib PNG output

Use `--output` to control where the rendered PNG goes:

| Value | Behaviour |
|---|---|
| *(omitted)* or `auto` | Inline display if the terminal supports it; otherwise write an auto-named file |
| `inline` | Force inline display; warn and fall back to file if no protocol detected |
| `-` | Write raw PNG bytes to stdout (no terminal escape sequences — useful for piping) |
| `path/to/file.png` | Write to the named file |

```
termseries --output chart.png yahoo TSLA
termseries --output - yahoo TSLA | display   # pipe to ImageMagick
termseries --output inline yahoo TSLA
```

Use `--protocol` to override which inline graphics protocol is used (default: `auto`):

| Value | Protocol |
|---|---|
| `auto` | Auto-detect from terminal environment (default) |
| `kitty` | Kitty Terminal Graphics Protocol |
| `iterm2` | iTerm2 OSC 1337 Inline Images Protocol |
| `sixel` | Sixel graphics |

This is especially useful inside tmux or other multiplexers where terminal detection can fail:

```
termseries --output inline --protocol iterm2 yahoo TSLA
```

Both options can be persisted in `termseries.env`:

```ini
# termseries.env
OUTPUT=inline
PROTOCOL=kitty
```

Precedence (highest to lowest): CLI flag → config file → auto-detection.

## Plotly HTML output

`--backend plotly` writes self-contained HTML. `--output auto` saves an automatically
named `.html` file; `--output report.html` writes an explicit path; `--output -`
writes UTF-8 HTML to stdout. `--open` opens a saved file. `--html-fragment` exports
markup and scripts for an existing document. Inline PNG protocols and clipboard
copy are not supported by this backend.

See [Browser charts and Python](browser.md) for embedding, size/theme settings,
and the distinction between browser snapshots and the live terminal UI.
