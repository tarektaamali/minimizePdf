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


def test_readme_is_french_and_mentions_the_output_folder():
    text = (ROOT / "LISEZ-MOI.txt").read_text(encoding="utf8")
    assert "PDF-réduits" in text
    assert "Installer.bat" in text
    assert "vérifier avant" in text


@windows_only
def test_launcher_uses_pythonw_so_no_console_appears():
    text = (ROOT / "Réduire PDF.bat").read_text(encoding="utf8")
    assert "pythonw.exe" in text
    assert "python.exe" not in text.replace("pythonw.exe", "")
    assert "chcp 65001" in text


@windows_only
def test_installer_creates_a_desktop_shortcut():
    text = (ROOT / "Installer.bat").read_text(encoding="utf8")
    assert "WScript.Shell" in text
    assert "Réduire PDF.lnk" in text
    assert "GetFolderPath('Desktop')" in text


@windows_only
def test_the_server_starts_and_serves_the_page():
    """Skips until pdfshrink/web.py exists (parent plan, Task 8)."""
    pytest.importorskip("pdfshrink.web")
    import socket
    import threading
    import time
    import urllib.request

    from pdfshrink import web

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    app = web.create_app()
    thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, use_reloader=False),
        daemon=True)
    thread.start()
    for _ in range(50):
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/" % port) as r:
                assert r.status == 200
                return
        except Exception:
            time.sleep(0.1)
    pytest.fail("the server did not answer on 127.0.0.1:%d" % port)


def test_batch_files_use_crlf_line_endings():
    """cmd.exe reads batch files by byte offset and loses sync on LF-only
    endings: `set` became `"APP=` and `powershell` became `ershell`. A file
    can appear to work and break as soon as an edit shifts the offsets."""
    for name in ("Installer.bat", "Réduire PDF.bat"):
        data = (ROOT / name).read_bytes()
        crlf = data.count(b"\r\n")
        lf_only = data.count(b"\n") - crlf
        assert lf_only == 0, "%s has %d LF-only line endings" % (name, lf_only)
        assert crlf > 0, "%s has no line endings at all" % name


@windows_only
def test_batch_files_force_utf8_output():
    """format_size emits U+202F, which Windows' default cp1252 console
    encoding cannot represent: printing a size raises UnicodeEncodeError.
    PYTHONUTF8=1 is what stops that reaching the user."""
    for name in ("Installer.bat", "Réduire PDF.bat"):
        text = (ROOT / name).read_text(encoding="utf8")
        assert "PYTHONUTF8=1" in text, "%s does not force UTF-8" % name
