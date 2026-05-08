"""Docker build verification tests."""

import subprocess

import pytest

pytestmark = pytest.mark.docker


def test_docker_build() -> None:
    """Verify Docker image builds successfully."""
    result = subprocess.run(
        ["docker", "compose", "build"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Docker build failed: {result.stderr}"


def test_docker_run_help() -> None:
    """Verify the Docker container runs and the CLI is installed."""
    result = subprocess.run(
        ["docker", "compose", "run", "--rm", "app", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Docker run failed: {result.stderr}"
    assert "termseries" in result.stdout


def test_docker_yahoo() -> None:
    """Verify the yahoo subcommand fetches and renders a chart."""
    result = subprocess.run(
        ["docker", "compose", "run", "--rm", "app", "yahoo", "TSLA", "AAPL", "MSFT"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"yahoo subcommand failed: {result.stderr}"
    assert result.stdout.strip(), "Expected chart output on stdout"
