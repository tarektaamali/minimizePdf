"""Where results go, and how to show them to the user.

Every platform difference in this project lives in this file. Nothing else
branches on sys.platform, which is what keeps the macOS build working while
development happens on Windows.
"""

import os
import subprocess
import sys

OUTPUT_FOLDER = "PDF-réduits"


def _windows_desktop():
    """Ask the shell, because OneDrive redirects Desktop on many machines."""
    import ctypes
    import ctypes.wintypes as wintypes
    import uuid

    class _GUID(ctypes.Structure):
        _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD),
                    ("d3", wintypes.WORD), ("d4", ctypes.c_byte * 8)]

    folder = uuid.UUID("B4BFCC3A-DB2C-424C-B029-7FE99A87C641")   # Desktop
    guid = _GUID()
    guid.d1, guid.d2, guid.d3 = folder.fields[0], folder.fields[1], \
        folder.fields[2]
    guid.d4 = (ctypes.c_byte * 8)(
        *[b - 256 if b > 127 else b for b in folder.bytes[8:]])

    out = ctypes.c_wchar_p()
    rc = ctypes.windll.shell32.SHGetKnownFolderPath(
        ctypes.byref(guid), 0, None, ctypes.byref(out))
    if rc != 0 or not out.value:
        return os.path.expanduser("~/Desktop")
    return out.value


def desktop_dir():
    if sys.platform == "win32":
        return _windows_desktop()
    return os.path.expanduser("~/Desktop")


def output_dir():
    """The PDF-réduits folder, created if it does not exist."""
    path = os.path.join(desktop_dir(), OUTPUT_FOLDER)
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def reveal(path):
    """Show a folder to the user. Never raises: this is a convenience.

    explorer.exe returns 1 even when it succeeds, so its exit code is not
    checked and Popen is used rather than run().
    """
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass
