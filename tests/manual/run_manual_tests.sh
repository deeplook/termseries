#!/usr/bin/env bash
# Run from project root. Requires: asciinema, iTerm2, Ghostty, WezTerm installed.
#
# NOTE: This script opens GUI terminal windows and MUST be run in a local desktop
# session. It will NOT work over SSH. If you are connected via SSH, play the casts
# manually instead — see tests/manual/TESTPLAN.md for instructions.
set -euo pipefail

if [[ -n "${SSH_CONNECTION:-}" || -n "${SSH_CLIENT:-}" ]]; then
    echo "ERROR: SSH session detected. This script requires a local desktop session."
    echo "Play the casts manually in each terminal instead:"
    echo "  asciinema play tests/manual/casts/test_iterm2_protocol.cast   # in iTerm2"
    echo "  asciinema play tests/manual/casts/test_kitty_protocol.cast    # in Ghostty"
    echo "  asciinema play tests/manual/casts/test_sixel_protocol.cast    # in WezTerm"
    exit 1
fi

ROOT="$(pwd)"
CASTS="$ROOT/tests/manual/casts"

echo "=== Opening iTerm2 (OSC 1337 protocol) ==="
osascript <<APPLESCRIPT
tell application "iTerm2"
  activate
  create window with default profile command "asciinema play $CASTS/test_iterm2_protocol.cast"
end tell
APPLESCRIPT

echo "=== Opening Ghostty (Kitty/APC protocol) ==="
ghostty -- bash -c "asciinema play $CASTS/test_kitty_protocol.cast; echo 'Done. Press Enter to close.'; read" &

echo "=== Opening WezTerm (Sixel/DCS protocol) ==="
wezterm start -- bash -c "asciinema play $CASTS/test_sixel_protocol.cast; echo 'Done. Press Enter to close.'; read" &

echo "=== All three terminal windows opened ==="
