"""requirements.txt must be installable on every interpreter we support.

Windows brings its own Python 3.12 through uv; macOS has no installer and
uses the system interpreter, which is 3.9. A pin that quietly requires 3.10
makes `pip install -r requirements.txt` fail on macOS with nothing but a
resolver error, so these tests pin the contract instead.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).parent.parent
REQUIREMENTS = ROOT / "requirements.txt"

SUPPORTED = ("3.9", "3.12")
NEEDED = ("pikepdf", "pypdfium2", "pillow", "numpy", "scipy", "flask",
          "zstandard")

LINE = re.compile(
    r"^(?P<name>[A-Za-z0-9._-]+)==(?P<version>[^\s;]+)"
    r"(?:\s*;\s*python_version\s*(?P<op><=|>=|<|>|==)\s*[\"'](?P<bound>[^\"']+)[\"'])?$"
)


def _parse():
    out = []
    for raw in REQUIREMENTS.read_text(encoding="utf8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = LINE.match(line)
        assert match, "cannot parse requirement: %r" % raw
        out.append(match.groupdict())
    return out


def _as_tuple(text):
    return tuple(int(part) for part in text.split("."))


def _applies(entry, python):
    if entry["op"] is None:
        return True
    left, right = _as_tuple(python), _as_tuple(entry["bound"])
    return {
        ">=": left >= right, ">": left > right,
        "<=": left <= right, "<": left < right,
        "==": left == right,
    }[entry["op"]]


def test_every_package_resolves_on_every_supported_python():
    entries = _parse()
    for python in SUPPORTED:
        for name in NEEDED:
            matching = [e for e in entries
                        if e["name"].lower() == name and _applies(e, python)]
            assert matching, (
                "%s has no version for Python %s; `pip install -r "
                "requirements.txt` would fail there" % (name, python))
            assert len(matching) == 1, (
                "%s resolves to %d versions on Python %s: %s"
                % (name, len(matching), python,
                   [e["version"] for e in matching]))


def test_the_installed_versions_are_the_ones_pinned_for_this_python():
    """What the suite actually runs against must be what we ship."""
    import sys
    from importlib import metadata

    python = "%d.%d" % sys.version_info[:2]
    entries = _parse()
    for name in NEEDED:
        try:
            installed = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
        wanted = [e["version"] for e in entries
                  if e["name"].lower() == name and _applies(e, python)]
        if wanted:
            assert installed == wanted[0], (
                "%s %s is installed but requirements.txt pins %s for Python "
                "%s" % (name, installed, wanted[0], python))
