import os
import subprocess
import sys

import pytest

from pdfshrink import platform_paths


def test_desktop_dir_exists():
    path = platform_paths.desktop_dir()
    assert isinstance(path, str)
    assert os.path.isdir(path), path


def test_output_dir_is_created_and_named_in_french(tmp_path, monkeypatch):
    monkeypatch.setattr(platform_paths, "desktop_dir", lambda: str(tmp_path))
    created = platform_paths.output_dir()
    assert os.path.basename(created) == "PDF-réduits"
    assert os.path.isdir(created)
    assert platform_paths.output_dir() == created      # idempotent


def test_reveal_never_raises_when_the_launcher_fails(monkeypatch, tmp_path):
    """reveal is a convenience; a failure to open a window is not an error.

    Patched rather than run for real, so the suite never pops a file
    manager window open on someone's desktop.
    """
    def boom(*args, **kwargs):
        raise OSError("no such program")

    monkeypatch.setattr(subprocess, "Popen", boom)
    platform_paths.reveal(str(tmp_path))


def test_reveal_uses_open_on_macos(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: seen.append(argv))
    platform_paths.reveal(str(tmp_path))
    assert seen and seen[0][0] == "open"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_reveal_uses_explorer_on_windows(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: seen.append(argv))
    platform_paths.reveal(str(tmp_path))
    assert seen and seen[0][0] == "explorer"
