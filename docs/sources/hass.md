# Home Assistant

The `hass` subcommand connects to a running Home Assistant instance via the
REST API. Set these environment variables:

```bash
export HASS_SERVER=http://homeassistant.local:8123
export HASS_TOKEN=your_long_lived_access_token
```

Create a long-lived access token in HASS under **Profile > Security > Long-Lived
Access Tokens**. The unit label (y-axis) is auto-detected from the entity's
`unit_of_measurement` attribute; use `--unit` to override.

```sh
termseries hass sensor.living_room_temperature --last 3h
termseries --gaps show hass sensor.living_room_temperature --last 7d
termseries -i hass sensor.power_consumption
```

The `hass` subcommand uses the same `--last` syntax and auto-detects the unit
from the entity's attributes. Entity IDs may include glob-style patterns
(`*` matches any run of characters, `?` matches a single character),
expanded against all entities currently known to Home Assistant:

```bash
# Plot every sensor whose ID contains "battery_level"
termseries hass "sensor.*battery_level" --period 7d
```

Quote patterns so your shell doesn't expand them first. The match isn't
anchored to the end, so `sensor.*battery_level` also matches
`sensor.phone_battery_level_2`.
