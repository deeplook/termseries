# Configuration

## Source environment variables

| Variable | Effect |
|---|---|
| `HASS_SERVER` | Home Assistant base URL (e.g. `http://ha.local:8123`) |
| `HASS_TOKEN` | Home Assistant long-lived access token |

## Theme and config files

Use `--theme dark|light|auto` to control the plot theme. The default is `auto`, which detects the terminal background for Matplotlib and follows browser color preference for Plotly.

```
termseries --theme dark yahoo TSLA
```

To persist the setting, create a `termseries.env` config file. Termseries searches for (first found wins):

1. `.termseries.env` in the current working directory
2. `~/.config/termseries/termseries.env`

```ini
# termseries.env
THEME=dark
```

See [`termseries.env.example`](assets/termseries.env.example) for a commented template.

Precedence (highest to lowest): `--theme` flag → config file → auto-detection.

Configuration can also persist `OUTPUT` and `PROTOCOL`; see [Output](output.md).
Explicit CLI settings take precedence. Browser output rejects incompatible
resolved settings, so override a saved inline protocol with `--protocol auto`
and choose an HTML file path when switching backends.
