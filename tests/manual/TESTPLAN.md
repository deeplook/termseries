# Manual Inline Image Protocol Test Plan

## Context

termseries supports three inline image protocols (iTerm2/OSC-1337, Kitty/APC, Sixel) across
different terminal emulators. This test plan validates that asciicasts generated with
`gen_asciicast.py` — containing captured inline-image escape sequences — play back correctly
in the matching terminal.

| Terminal | Supported Protocol | Protocol Detection Env Var |
|----------|-------------------|---------------------------|
| iTerm2   | iTerm2 (OSC 1337) | `TERM_PROGRAM=iTerm.app`  |
| Ghostty  | Kitty (APC)       | `TERM` starts with `xterm-ghostty` |
| WezTerm  | Sixel (DCS)       | `TERM_PROGRAM=WezTerm`    |

The key insight: `gen_asciicast.py` sets `TERM=xterm-256color` in the PTY — no protocol is
auto-detected. Each YAML spec explicitly forces `--protocol X --output inline`.

---

## Files

```
tests/manual/
├── TESTPLAN.md                 # This document
├── test_iterm2_protocol.yaml   # YAML spec → iTerm2 OSC-1337 cast
├── test_kitty_protocol.yaml    # YAML spec → Kitty/APC cast (for Ghostty)
├── test_sixel_protocol.yaml    # YAML spec → Sixel cast (for WezTerm)
├── generate_test_casts.sh      # Step 1: generate the 3 cast files
└── run_manual_tests.sh         # Step 2: open each terminal for eyeball tests

tests/manual/casts/
├── test_iterm2_protocol.cast
├── test_kitty_protocol.cast
└── test_sixel_protocol.cast
```

---

## Running the Tests

### Step 1: Generate casts (requires network — fetches live stock data for ticker A)

```bash
# From project root:
bash tests/manual/generate_test_casts.sh
```

Verify cast headers:

```bash
head -1 tests/manual/casts/test_iterm2_protocol.cast  # should show {"version": 3, ...}
```

Verify protocol-specific escape sequences are present:

```bash
# iTerm2 (OSC 1337)
grep -c "1337;File" tests/manual/casts/test_iterm2_protocol.cast

# Kitty (APC) — sequences begin with ESC _G
python3 -c "
import json
data = open('tests/manual/casts/test_kitty_protocol.cast').read()
print(data.count('\\x1b_G'))
"

# Sixel (DCS) — sequences begin with ESC P
python3 -c "
import json
data = open('tests/manual/casts/test_sixel_protocol.cast').read()
print(data.count('\\x1bP'))
"
```

### Step 2: Eyeball test in each terminal

**Requires a local desktop session — does not work over SSH.**

The script opens all three terminals simultaneously, each playing its respective cast:

```bash
# From project root:
bash tests/manual/run_manual_tests.sh
```

If you are on SSH or prefer to run them manually, open each terminal yourself and run:

```bash
# In iTerm2 — tests OSC 1337 inline image protocol:
asciinema play tests/manual/casts/test_iterm2_protocol.cast

# In Ghostty — tests Kitty/APC inline image protocol:
asciinema play tests/manual/casts/test_kitty_protocol.cast

# In WezTerm — tests Sixel/DCS inline image protocol:
asciinema play tests/manual/casts/test_sixel_protocol.cast
```

Each cast replays a live `termseries` run with the matching protocol forced via
`--protocol <X> --output inline`. The chart should appear as an inline image, not
raw escape codes. Playing a cast in the wrong terminal (e.g. the Kitty cast in
iTerm2) will likely show garbage or a blank region — that is expected.

---

## Eyeball Test Checklist

### PASS criteria (all three terminals)

- [ ] Terminal shows the stock chart rendered as an inline image (not raw escape codes)
- [ ] Chart occupies the correct width and is not clipped
- [ ] No visible garbage characters around the image
- [ ] asciinema playback timing looks natural (typing animation before chart appears)

### FAIL criteria

- ESC sequences printed as literal text (e.g. `^[]1337;File=...` or `^[_G...`)
- Terminal shows only a blank region where the image should be
- asciinema errors out on playback

---

## Cast-to-Terminal Mapping

| Cast file                      | Play in  | Protocol       |
|-------------------------------|----------|----------------|
| `test_iterm2_protocol.cast`   | iTerm2   | OSC 1337       |
| `test_kitty_protocol.cast`    | Ghostty  | Kitty/APC      |
| `test_sixel_protocol.cast`    | WezTerm  | Sixel/DCS      |

---

## Automation Notes

| Terminal | Automation Method | Confidence |
|----------|------------------|-----------|
| iTerm2   | AppleScript `create window with default profile command "..."` | High |
| Ghostty  | `ghostty -- bash -c "..."` CLI flag | Medium — `ghostty` must be in PATH |
| WezTerm  | `wezterm start -- bash -c "..."` | High |

The script cannot automate the visual correctness check — that remains a human eyeball test.

---

## Critical Files

- `gen_asciicast.py` — cast generator (PTY-based, sets `TERM=xterm-256color`)
- `src/termseries/terminal.py` — `_print_kitty_png`, `_print_iterm2_png`, `_print_sixel_png`
- `src/termseries/cli.py` — `--protocol` flag
- `src/termseries/render.py` — protocol dispatch chain
