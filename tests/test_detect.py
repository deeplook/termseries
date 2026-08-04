"""Tests for termseries.detect module."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from termseries.detect import (
    _read_response,
    detect_supported_image_protocols,
    supports_iterm2_inline_images,
    supports_kitty_graphics,
    supports_sixel,
)

# ===================================================================
# _read_response
# ===================================================================


class TestReadResponse:
    def test_stdin_fileno_raises_returns_empty(self) -> None:
        """If stdin.fileno() raises, return b''."""
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.fileno.side_effect = Exception("no fileno")
            assert _read_response(0.1) == b""

    def test_stdin_not_tty_returns_empty(self) -> None:
        """If stdin fd is not a tty, return b''."""
        with (
            patch("sys.stdin") as mock_stdin,
            patch("termseries.detect.os.isatty", return_value=False),
        ):
            mock_stdin.fileno.return_value = 0
            assert _read_response(0.1) == b""

    def test_no_termios_returns_empty(self) -> None:
        """On platforms without termios/tty (e.g. Windows), return b'' up front."""
        with (
            patch("termseries.detect.termios", None),
            patch("termseries.detect.tty", None),
        ):
            assert _read_response(0.1) == b""

    @pytest.mark.skipif(
        sys.platform == "win32", reason="mocks termios/tty, which don't exist here"
    )
    def test_tty_reads_data_until_quiet(self) -> None:
        """With a real tty, read data until stream goes quiet."""
        with (
            patch("sys.stdin") as mock_stdin,
            patch("termseries.detect.os.isatty", return_value=True),
            patch("termseries.detect.termios.tcgetattr", return_value=[]),
            patch("termseries.detect.tty.setraw"),
            patch("termseries.detect.termios.tcsetattr"),
            patch(
                "termseries.detect.select.select",
                side_effect=[
                    ([0], [], []),  # first call: data ready
                    ([], [], []),  # second call: quiet — break
                ],
            ),
            patch("termseries.detect.os.read", return_value=b"\x1b_Gresp\x1b\\"),
        ):
            mock_stdin.fileno.return_value = 0
            result = _read_response(0.5)
        assert result == b"\x1b_Gresp\x1b\\"

    @pytest.mark.skipif(
        sys.platform == "win32", reason="mocks termios/tty, which don't exist here"
    )
    def test_tty_empty_read_breaks(self) -> None:
        """An empty os.read() (EOF) breaks the loop."""
        with (
            patch("sys.stdin") as mock_stdin,
            patch("termseries.detect.os.isatty", return_value=True),
            patch("termseries.detect.termios.tcgetattr", return_value=[]),
            patch("termseries.detect.tty.setraw"),
            patch("termseries.detect.termios.tcsetattr"),
            patch("termseries.detect.select.select", return_value=([0], [], [])),
            patch("termseries.detect.os.read", return_value=b""),
        ):
            mock_stdin.fileno.return_value = 0
            result = _read_response(0.5)
        assert result == b""


# ===================================================================
# supports_iterm2_inline_images
# ===================================================================


class TestSupportsIterm2InlineImages:
    def _call(self, response: bytes) -> bool:
        mock_stdout = MagicMock()
        with (
            patch("sys.stdout", mock_stdout),
            patch("termseries.detect._read_response", return_value=response),
        ):
            return supports_iterm2_inline_images()

    def test_returns_true_when_capability_f_present(self) -> None:
        assert self._call(b"\x1b]1337;Capabilities=F\x1b\\") is True

    def test_returns_false_when_no_capabilities(self) -> None:
        assert self._call(b"") is False

    def test_returns_false_when_f_missing(self) -> None:
        assert self._call(b"Capabilities=XY") is False


# ===================================================================
# supports_kitty_graphics
# ===================================================================


class TestSupportsKittyGraphics:
    def _call(self, response: bytes) -> bool:
        mock_stdout = MagicMock()
        with (
            patch("sys.stdout", mock_stdout),
            patch("termseries.detect._read_response", return_value=response),
        ):
            return supports_kitty_graphics()

    def test_returns_true_when_apc_in_response(self) -> None:
        assert self._call(b"\x1b_Gi=31;OK\x1b\\") is True

    def test_returns_false_when_no_apc(self) -> None:
        assert self._call(b"\x1b[?64;1;2c") is False

    def test_returns_false_when_empty(self) -> None:
        assert self._call(b"") is False


# ===================================================================
# supports_sixel
# ===================================================================


class TestSupportsSixel:
    def _call(self, response: bytes) -> bool:
        mock_stdout = MagicMock()
        with (
            patch("sys.stdout", mock_stdout),
            patch("termseries.detect._read_response", return_value=response),
        ):
            return supports_sixel()

    def test_returns_true_when_param_4_present(self) -> None:
        # DA response: ESC [ ? 64 ; 1 ; 4 ; 22 c
        assert self._call(b"\x1b[?64;1;4;22c") is True

    def test_returns_false_when_param_4_absent(self) -> None:
        assert self._call(b"\x1b[?64;1;22c") is False

    def test_returns_false_when_no_bracket(self) -> None:
        assert self._call(b"no bracket here") is False

    def test_returns_false_when_empty(self) -> None:
        assert self._call(b"") is False

    def test_handles_question_mark_prefix(self) -> None:
        """The '?' in DA responses is treated as a ';' separator."""
        assert self._call(b"\x1b[?4c") is True


# ===================================================================
# detect_supported_image_protocols
# ===================================================================


class TestDetectSupportedImageProtocols:
    def test_returns_dict_with_all_keys(self) -> None:
        with (
            patch(
                "termseries.detect.supports_iterm2_inline_images", return_value=False
            ),
            patch("termseries.detect.supports_kitty_graphics", return_value=True),
            patch("termseries.detect.supports_sixel", return_value=False),
        ):
            result = detect_supported_image_protocols()
        assert result == {"iterm2": False, "kitty": True, "sixel": False}
