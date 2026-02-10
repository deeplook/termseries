"""Shared fixtures for termseries tests."""

from datetime import datetime, timezone
from io import BytesIO

import pytest
from PIL import Image as PILImage

from termseries import TimeSeries


@pytest.fixture()
def small_png() -> bytes:
    """A minimal 2x3 red PNG created via Pillow."""
    img = PILImage.new("RGB", (2, 3), color=(255, 0, 0))
    buf = BytesIO()
    img.save(buf, format="png")
    return buf.getvalue()


@pytest.fixture()
def large_png() -> bytes:
    """A PNG large enough that its base64 exceeds one 4096-byte chunk."""
    import random

    rng = random.Random(42)
    img = PILImage.new("RGB", (200, 200))
    pixels = [
        (rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255))
        for _ in range(200 * 200)
    ]
    img.putdata(pixels)
    buf = BytesIO()
    img.save(buf, format="png")
    return buf.getvalue()


@pytest.fixture()
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all terminal-detection env vars so tests start clean."""
    for var in (
        "TERM",
        "TERM_PROGRAM",
        "LC_TERMINAL",
        "ITERM_SESSION_ID",
        "SSH_CONNECTION",
        "SSH_CLIENT",
        "TERMSERIES_DARK",
        "TERMSERIES_LIGHT",
        "TERMSERIES_FORCE_INLINE",
        "TERMSERIES_NO_INLINE",
        "COLORFGBG",
        "ITERM_PROFILE",
        "WAYLAND_DISPLAY",
    ):
        monkeypatch.delenv(var, raising=False)


def make_series(n: int = 5, base: float = 100.0) -> TimeSeries:
    """Return a synthetic TimeSeries with *n* daily points."""
    return [
        (datetime(2024, 1, 1 + i, tzinfo=timezone.utc), base + i * 1.5)
        for i in range(n)
    ]
