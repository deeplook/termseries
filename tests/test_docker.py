"""Docker build verification tests."""

import subprocess


def test_docker_build() -> None:
    """Verify Docker image builds successfully."""
    result = subprocess.run(
        ["docker", "compose", "build"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Docker build failed: {result.stderr}"
