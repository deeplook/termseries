"""Terminal detection, inline image printing, clipboard, and display helpers."""

from __future__ import annotations

import base64
import os
import struct
import subprocess
import sys
import tempfile
from io import BytesIO
from pathlib import Path

import typer
from dotenv import dotenv_values


def _print_kitty_png(png_bytes: bytes) -> None:
    """Print a PNG inline using Kitty's Terminal Graphics Protocol."""
    import shutil

    cols = shutil.get_terminal_size().columns
    b64 = base64.b64encode(png_bytes).decode("ascii")
    first = True
    while b64:
        chunk, b64 = b64[:4096], b64[4096:]
        m = 1 if b64 else 0
        if first:
            sys.stdout.write(f"\033_Ga=T,f=100,c={cols},m={m};{chunk}\033\\")
            first = False
        else:
            sys.stdout.write(f"\033_Gm={m};{chunk}\033\\")
    sys.stdout.write("\n")


def _print_sixel_png(png_bytes: bytes) -> None:
    """Print a PNG inline as Sixel graphics."""
    from PIL import Image as PILImage
    from textual_image.renderable import sixel

    img = PILImage.open(BytesIO(png_bytes))
    # image_to_sixels works at runtime but is not an explicitly exported attribute.
    sys.stdout.write(sixel.image_to_sixels(img))  # type: ignore[attr-defined]
    sys.stdout.write("\n")


def _print_iterm2_png(png_bytes: bytes) -> None:
    """Print a PNG to iTerm2 using the Inline Images Protocol.

    Uses width=100% to fill all available horizontal space.
    """
    b64 = base64.b64encode(png_bytes).decode("ascii")
    sys.stdout.write("\033]1337;File=inline=1;width=100%;preserveAspectRatio=1:")
    sys.stdout.write(b64)
    sys.stdout.write("\a\n")


def _is_kitty() -> bool:
    """Return True if running inside the Kitty terminal."""
    return (
        os.environ.get("TERM", "").startswith("xterm-kitty")
        or os.environ.get("TERM_PROGRAM") == "kitty"
    )


def _is_ghostty() -> bool:
    """Return True if running inside the Ghostty terminal."""
    return os.environ.get("TERM", "").startswith("xterm-ghostty")


def _is_iterm2() -> bool:
    """Return True if the current process appears to be running under iTerm2."""
    return (
        os.environ.get("TERM_PROGRAM") == "iTerm.app"
        or os.environ.get("LC_TERMINAL") == "iTerm2"
        or "ITERM_SESSION_ID" in os.environ
    )


def _is_sixel_terminal() -> bool:
    """Return True for terminals known to support Sixel graphics."""
    term_program = os.environ.get("TERM_PROGRAM", "")
    if term_program in ("WezTerm", "vscode"):
        return True
    term = os.environ.get("TERM", "")
    return term.startswith("foot") or term.startswith("mlterm") or term == "xterm"


def _png_dimensions(png_bytes: bytes) -> tuple[int, int]:
    """Read width and height from a PNG's IHDR chunk."""
    w, h = struct.unpack(">II", png_bytes[16:24])
    return w, h


def _terminal_pixel_width() -> int | None:
    """Return the terminal width in pixels via TIOCGWINSZ, or None if unavailable."""
    try:
        import fcntl
        import termios

        result = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b"\x00" * 8)
        _rows, _cols, xpixels, _ypixels = struct.unpack("HHHH", result)
        if xpixels > 0:
            return int(xpixels)
    except Exception:
        pass
    return None


def _is_ssh_session() -> bool:
    """Return True if running inside an SSH session."""
    return bool(os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT"))


def _is_docker() -> bool:
    """Return True if running inside a Docker container."""
    return Path("/.dockerenv").exists()


def _copy_to_clipboard(png_bytes: bytes) -> None:
    """Copy PNG image bytes to the system clipboard.

    Uses platform-specific commands via subprocess.
    """
    if sys.platform == "darwin":
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(png_bytes)
            tmp = f.name
        try:
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    "set the clipboard to "
                    f'(read (POSIX file "{tmp}") as \u00abclass PNGf\u00bb)',
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        finally:
            os.unlink(tmp)
    elif sys.platform == "win32":
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(png_bytes)
            tmp = f.name
        try:
            ps_script = (
                "Add-Type -Assembly System.Windows.Forms;"
                "[System.Windows.Forms.Clipboard]::SetImage("
                f"[System.Drawing.Image]::FromFile('{tmp}'))"
            )
            subprocess.run(["powershell", "-Command", ps_script], check=True)
        finally:
            os.unlink(tmp)
    elif os.environ.get("WAYLAND_DISPLAY"):
        subprocess.run(
            ["wl-copy", "--type", "image/png"],
            input=png_bytes,
            check=True,
        )
    else:
        subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "image/png"],
            input=png_bytes,
            check=True,
        )


def _parse_ratio(value: str) -> tuple[int, int]:
    """Parse ratio strings like ``"4:1"`` or ``"16:10"`` into ``(w, h)``."""
    s = value.strip()
    parts = s.split(":")
    if len(parts) != 2:
        raise typer.BadParameter('ratio must look like "4:1" or "16:10"')
    w_s, h_s = (p.strip() for p in parts)
    if not w_s or not h_s:
        raise typer.BadParameter('ratio must look like "4:1" or "16:10"')
    try:
        w = int(w_s)
        h = int(h_s)
    except ValueError as e:
        raise typer.BadParameter('ratio must use integers like "4:1"') from e
    if w <= 0 or h <= 0:
        raise typer.BadParameter("ratio components must be positive")
    return w, h


_VALID_THEMES = frozenset({"dark", "light", "auto"})
_VALID_OUTPUTS = frozenset({"auto", "inline", "-"})
_VALID_PROTOCOLS = frozenset({"auto", "kitty", "iterm2", "sixel"})


def _load_config() -> dict[str, str]:
    """Load settings from the first found termseries.env config file.

    Searches (first found wins):
    1. .termseries.env in the current working directory
    2. ~/.config/termseries/termseries.env
    """
    candidates = [
        Path.cwd() / ".termseries.env",
        Path.home() / ".config" / "termseries" / "termseries.env",
    ]
    for path in candidates:
        if path.exists():
            raw = dotenv_values(path)
            return {k.lower(): v for k, v in raw.items() if v is not None}
    return {}


def _detect_dark_terminal(theme: str) -> bool:
    """Return True if the dark theme should be used.

    Parameters
    ----------
    theme:
        "dark" or "light" short-circuits immediately.
        "auto" runs heuristics (COLORFGBG, iTerm2 profile) and falls back to dark.
    """
    if theme == "dark":
        return True
    if theme == "light":
        return False

    # NO_COLOR signals the user wants minimal color; treat as light theme
    if "NO_COLOR" in os.environ:
        return False

    # auto: run heuristics
    colorfgbg = os.environ.get("COLORFGBG")
    if colorfgbg:
        parts = colorfgbg.split(";")
        try:
            bg = int(parts[-1])
        except ValueError:
            bg = None
        if bg is not None and 0 <= bg <= 15:
            return bg <= 8

    iterm_profile = (os.environ.get("ITERM_PROFILE") or "").lower()
    if "dark" in iterm_profile:
        return True
    return "light" not in iterm_profile
