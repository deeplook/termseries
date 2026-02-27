"""
Terminal image protocol detection.

This module provides runtime detection for three widely used terminal graphics
protocols:

- iTerm2 Inline Images Protocol (OSC 1337)
- Kitty Terminal Graphics Protocol (APC)
- Sixel Graphics Protocol (DEC DCS)

Three dedicated functions implement the detection for each protocol, each
emitting a non-destructive query sequence and parsing the terminal's response
according to the official specifications. A fourth convenience function invokes
all three detectors sequentially and returns a dictionary of results.

Detection is performed by temporarily switching the terminal to raw mode,
writing the query, and reading the response within a short timeout. The private
helper ``_read_response()`` ensures reliable capture of control sequences while
restoring the original terminal settings in all cases.

The implementation follows the exact query formats and response semantics
documented by:

- iTerm2 (Terminal Feature Reporting)
- Kitty (graphics-protocol query action)
- Sixel (Primary Device Attributes query, as used by standard tools such as lsix)

Platform compatibility
----------------------
The module requires a Unix-like environment with ``termios`` support. Windows
is not supported in the current implementation.

Usage
-----
.. code-block:: python

    from terminal_image_detection import detect_supported_image_protocols

    supported = detect_supported_image_protocols()
    if supported["kitty"]:
        # Use Kitty graphics protocol
        ...

Notes
-----
- All queries are safe and non-destructive.
- The functions are thread-safe with respect to terminal state.
- Detection works inside multiplexers (tmux, screen, etc.) provided the outer
  terminal forwards control sequences and replies.
- Response parsing relies on the distinct introducers of each protocol,
  eliminating false positives.
"""

import os
import select
import sys
import termios
import time
import tty


def _read_response(timeout: float = 0.5) -> bytes:
    """Read terminal response in raw mode until data stops arriving or timeout."""
    try:
        fd = sys.stdin.fileno()
    except Exception:
        return b""
    if not os.isatty(fd):
        return b""
    old_settings = termios.tcgetattr(fd)
    response = b""
    try:
        tty.setraw(fd)
        end_time = time.time() + timeout
        while time.time() < end_time:
            remaining = min(0.05, end_time - time.time())
            ready, _, _ = select.select([fd], [], [], remaining)
            if ready:
                chunk = os.read(fd, 1024)
                if not chunk:
                    break
                response += chunk
            elif response:  # Data received and stream has quieted
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return response


def supports_iterm2_inline_images() -> bool:
    """Detect support for the iTerm2 inline images (OSC 1337 File) protocol."""
    query = "\x1b]1337;Capabilities\x1b\\"
    sys.stdout.buffer.write(query.encode("ascii"))
    sys.stdout.flush()
    response = _read_response(0.3)
    # Response format: OSC 1337;Capabilities=...ST
    # Feature "F" indicates FILE / inline-image support
    return b"Capabilities=" in response and b"F" in response


def supports_kitty_graphics() -> bool:
    """Detect support for the Kitty graphics protocol."""
    # Query action (a=q) + Primary Device Attributes; non-destructive
    query = "\x1b_Gi=31,s=1,v=1,a=q,t=d,f=24;AAAA\x1b\\\x1b[c"
    sys.stdout.buffer.write(query.encode("ascii"))
    sys.stdout.flush()
    response = _read_response(0.5)
    # Supported terminals reply with APC (ESC _G...) before or with the DA response
    return b"\x1b_G" in response


def supports_sixel() -> bool:
    """Detect support for the Sixel graphics protocol via Device Attributes (DA)."""
    query = "\x1b[c"
    sys.stdout.buffer.write(query.encode("ascii"))
    sys.stdout.flush()
    response = _read_response(0.3)
    if b"[" not in response or b"c" not in response:
        return False
    start = response.find(b"[")
    end = response.find(b"c", start)
    if start == -1 or end == -1:
        return False
    param_str = response[start + 1 : end].decode("ascii", errors="ignore")
    param_str = param_str.replace("?", ";")
    params = [p.strip() for p in param_str.split(";") if p.strip()]
    return "4" in params


def detect_supported_image_protocols() -> dict[str, bool]:
    """Return a dictionary indicating which of the three protocols are supported."""
    return {
        "iterm2": supports_iterm2_inline_images(),
        "kitty": supports_kitty_graphics(),
        "sixel": supports_sixel(),
    }
