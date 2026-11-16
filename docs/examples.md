# Examples

```bash
# Plot stock prices (7-day default)
termseries yahoo TSLA AAPL MSFT

# Indexed comparison over 1 month
termseries --mode indexed yahoo --last 1mo TSLA AAPL MSFT

# Log scale over 5 years
termseries --mode log yahoo --last 5y AAPL MSFT GOOGL

# Drawdown chart
termseries --mode drawdown yahoo --last 1y TSLA AAPL

# Intra-day: 1-day period auto-picks 5-minute intervals
termseries yahoo TSLA --last 1d

# Explicit 1-minute interval override
termseries yahoo TSLA --interval 1m --last 1d

# Relative price ratio (exactly 2 tickers)
termseries --mode relative yahoo --last 1y AAPL MSFT

# Cumulative sum
termseries --mode cumulative csv sensor.csv --last 30d

# Point-to-point delta
termseries --mode delta yahoo TSLA --last 1mo

# Seasonal: overlay each year as its own line
termseries --mode seasonal yahoo TSLA --from 2022

# Seasonal: overlay each quarter (calendar-aligned, day-of-quarter x-axis)
termseries --mode seasonal --cycle quarter yahoo TSLA --last 2y

# Seasonal: overlay each week (Monday-Sunday x-axis)
termseries --mode seasonal --cycle 1w yahoo TSLA --last 6mo

# Custom title, no legend
termseries --title "TSLA vs AAPL" --no-legend yahoo TSLA AAPL --last 1y

# Show gaps in data (break lines where data is missing)
termseries --gaps show hass sensor.living_room_temperature --last 7d

# Connect gaps under 1 hour, break larger ones
termseries --gaps 1h csv sensor.csv --last 30d

# Step-style line (staircase effect)
termseries --line-style step-post yahoo TSLA --last 5d

# Display x-axis in your local timezone
termseries --tz local yahoo TSLA AAPL

# Display x-axis in a specific timezone
termseries --tz Europe/Berlin hass sensor.living_room_temperature --last 1d

# Copy plot to clipboard
termseries -c yahoo TSLA AAPL

# Interactive TUI
termseries -i yahoo TSLA

# --- Home Assistant sensors ---

# Plot HASS sensor data (requires HASS_SERVER and HASS_TOKEN env vars)
termseries hass sensor.living_room_temperature sensor.bedroom_temperature

# Last 3 hours of data
termseries hass sensor.living_room_temperature --last 3h

# Last 30 days with explicit unit
termseries hass sensor.living_room_temperature --last 30d --unit '°C'

# Glob pattern: plot every matching entity in one call
termseries hass "sensor.*battery_level" --last 7d

# Interactive TUI with HASS data
termseries -i hass sensor.power_consumption

# --- Polymarket markets ---

# Plot a Polymarket market's "yes" price
termseries polymarket will-bitcoin-hit-150k-in-2026

# Plot the "no" outcome instead
termseries polymarket will-bitcoin-hit-150k-in-2026 --outcome no

# Last 30 days
termseries polymarket will-bitcoin-hit-150k-in-2026 --last 30d

# --- CSV files ---

# Plot a local CSV (two columns: timestamp, value)
termseries csv /path/to/sensor.csv

# Multiple files, last 7 days, with a custom unit label
termseries csv temp.csv humidity.csv --last 7d --unit '°C'

# Headered CSV with multiple value columns: plots every column
termseries csv sensors.csv --last 7d

# Only plot specific columns from a headered CSV
termseries csv sensors.csv:temp,humidity --last 7d

# Non-standard periods work everywhere
termseries yahoo TSLA --last 14d
termseries yahoo TSLA --last 2w

# Calendar-anchored to-date periods
termseries yahoo TSLA --last ytd
termseries yahoo TSLA --last mtd
termseries hass sensor.power_consumption --last dtd

# Interactive TUI with CSV data
termseries -i csv sensor.csv

# --- Obsidian daily notes ---

# Plot numeric frontmatter fields from an Obsidian daily-notes folder
termseries obsidian ~/vault/Daily:mood,weight --last 90d
```

## Browser comparison

```sh
termseries --backend plotly --mode indexed --ratio 16:9 --theme light \
  --output stocks.html --open yahoo --last 1y TSLA NVDA
```

See the [renderer gallery](gallery.md) for nine direct Matplotlib/Plotly comparisons,
and [Browser charts and Python](browser.md) for embedding and programmatic use.
