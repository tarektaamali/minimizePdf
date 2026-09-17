"""The macOS launcher, mirroring tests/test_installer.py for Windows."""

import pathlib
import stat

ROOT = pathlib.Path(__file__).parent.parent


def test_launcher_is_executable_and_self_locating():
    launcher = ROOT / "scripts" / "Réduire PDF.command"
    assert launcher.exists()
    assert launcher.stat().st_mode & stat.S_IXUSR
    text = launcher.read_text(encoding="utf8")
    # Double-clicking a .command starts in the user's home, so the script
    # must find its own directory rather than assume the working one.
    assert "BASH_SOURCE" in text
    assert "pdfshrink.web" in text
    # Sizes carry U+202F; a non-UTF-8 console raises UnicodeEncodeError.
    assert "PYTHONUTF8" in text


def test_setup_script_creates_a_venv_and_survives_python_39():
    setup = (ROOT / "scripts" / "setup-mac.sh").read_text(encoding="utf8")
    assert "python3 -m venv" in setup
    # requirements.txt pins versions needing 3.10+, but the source targets
    # 3.9 so macOS system Python keeps working; setup must not hard-fail.
    assert "requirements.txt" in setup
    for package in ("pikepdf", "pypdfium2", "pillow", "numpy", "scipy", "flask"):
        assert package in setup
