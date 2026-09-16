"""The installer is testable for the first time now that development is on
Windows; on macOS these skip."""

import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent
windows_only = pytest.mark.skipif(sys.platform != "win32",
                                  reason="Windows installer")


def test_requirements_are_all_pinned():
    lines = (ROOT / "requirements.txt").read_text(encoding="utf8").split()
    assert lines, "requirements.txt is empty"
    for line in lines:
        assert "==" in line, "%s is not pinned" % line


@windows_only
def test_installer_pins_a_real_checksum():
    text = (ROOT / "Installer.bat").read_text(encoding="utf8")
    assert "PASTE_THE_HASH" not in text, "the uv checksum was never recorded"
    for line in text.splitlines():
        if line.strip().startswith("set \"UV_SHA256="):
            value = line.split("=", 1)[1].strip().strip('"')
            assert len(value) == 64, value
            int(value, 16)
            return
    pytest.fail("no UV_SHA256 line in Installer.bat")


@windows_only
def test_installer_never_requests_elevation():
    """An install that prompts for elevation is an install that does not
    happen on a managed machine."""
    text = (ROOT / "Installer.bat").read_text(encoding="utf8").lower()
    for forbidden in ("runas", "requestedexecutionlevel", "requireadministrator"):
        assert forbidden not in text, forbidden


@windows_only
def test_verify_install_succeeds_in_this_environment():
    """The same check the installer runs, against the dev virtualenv."""
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        pytest.skip("no .venv in the project")
    done = subprocess.run([str(python), str(ROOT / "verify_install.py")],
                          cwd=str(ROOT), capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "OK :" in done.stdout
