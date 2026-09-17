"""The macOS launcher, mirroring tests/test_installer.py for Windows."""

import pathlib
import stat

ROOT = pathlib.Path(__file__).parent.parent


def test_launcher_is_executable_and_self_locating():
    launcher = ROOT / "scripts" / "IntactPDF.command"
    assert launcher.exists()
    assert launcher.stat().st_mode & stat.S_IXUSR
    text = launcher.read_text(encoding="utf8")
    # Double-clicking a .command starts in the user's home, so the script
    # must find its own directory rather than assume the working one.
    assert "BASH_SOURCE" in text
    assert "pdfshrink.web" in text
    # Sizes carry U+202F; a non-UTF-8 console raises UnicodeEncodeError.
    assert "PYTHONUTF8" in text


def test_setup_script_installs_the_pinned_requirements():
    setup = (ROOT / "scripts" / "setup-mac.sh").read_text(encoding="utf8")
    assert "python3 -m venv" in setup
    # The pins carry environment markers for 3.9 and 3.12, so macOS installs
    # straight from the file with no special case. tests/test_requirements.py
    # is what guarantees that stays true.
    assert "pip install -q -r requirements.txt" in setup
