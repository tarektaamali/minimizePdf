"""Build the archive the user receives.

What ships is an explicit allow-list, never "the folder minus some things".
This project directory also holds the developer's own scanned documents, a
65 MB uv.exe, a 214 MB virtualenv and the test suite; a hand-made zip would
hand all of that to a non-technical person along with the application.

A deny-list runs as a second net, so a mistake in the allow-list fails the
build rather than shipping.

Run: python scripts/package.py [destination]
"""

import os
import pathlib
import sys
import zipfile

ROOT = pathlib.Path(__file__).parent.parent
FOLDER = "IntactPDF"
ARCHIVE = "Reduire-PDF.zip"          # no accent: the filename travels better

# Exactly what he needs, and nothing else.
FILES = [
    "Installer.bat",
    "IntactPDF.bat",
    "LISEZ-MOI.txt",
    "requirements.txt",
    "verify_install.py",
    "scripts/fetch_jbig2.py",
]
TREES = [
    ("pdfshrink", (".py",)),
    ("pdfshrink/static", (".html", ".css", ".js", ".ico")),
]

# Nothing matching these may appear in the archive, whatever the allow-list
# says. Personal documents first, because that is the one that matters.
FORBIDDEN_SUFFIXES = (".pdf", ".exe", ".dll", ".zip", ".conda", ".pyc")
FORBIDDEN_PARTS = ("__pycache__", ".venv", ".git", "tests", "docs",
                   "jbig2/", "journal.txt", ".pytest_cache")


def iter_sources():
    """Every file that will go into the archive, as absolute paths."""
    out = [ROOT / name for name in FILES]
    for folder, suffixes in TREES:
        base = ROOT / folder
        for path in sorted(base.iterdir()):
            if path.is_file() and path.suffix in suffixes:
                out.append(path)
    return out


def _check(arcname):
    lowered = arcname.lower()
    if lowered.endswith(FORBIDDEN_SUFFIXES):
        raise ValueError("refusing to package %s" % arcname)
    for part in FORBIDDEN_PARTS:
        if part in arcname:
            raise ValueError("refusing to package %s" % arcname)


def build(dest_dir=None):
    dest_dir = dest_dir or str(ROOT / "dist")
    if not os.path.isdir(dest_dir):
        os.makedirs(dest_dir)
    target = os.path.join(dest_dir, ARCHIVE)

    sources = iter_sources()
    missing = [p for p in sources if not p.exists()]
    if missing:
        raise FileNotFoundError("listed but absent: %s" % missing)

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sources:
            arcname = "%s/%s" % (FOLDER, path.relative_to(ROOT).as_posix())
            _check(arcname)
            # Written as bytes so batch files keep their CRLF endings.
            archive.writestr(arcname, path.read_bytes())
    return target


def main():
    dest = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        target = build(dest)
    except Exception as error:                   # noqa: BLE001
        print("ECHEC : %s" % error)
        return 1
    size = os.path.getsize(target)
    with zipfile.ZipFile(target) as archive:
        count = len(archive.namelist())
    print("OK : %s" % target)
    print("     %d fichiers, %.1f Ko" % (count, size / 1024.0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
