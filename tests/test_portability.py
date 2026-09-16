"""The Windows build dies the moment a Poppler or qpdf binary reappears.

Grepping this project's source is not enough: jbig2dec is spawned from
inside pikepdf, which is how it went unnoticed until the engine was first
run on Windows. These tests watch what is actually executed.
"""

import os
import pathlib
import subprocess

FORBIDDEN = ("qpdf", "pdfimages", "pdftoppm", "pdffonts", "pdftocairo",
             "jbig2dec")
PERMITTED = ("jbig2",)
PACKAGE = pathlib.Path(__file__).parent.parent / "pdfshrink"


def test_no_unix_binaries_referenced():
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        text = path.read_text(encoding="utf8")
        for name in FORBIDDEN:
            if '"%s"' % name in text or "'%s'" % name in text:
                offenders.append("%s references %s" % (path.name, name))
    assert not offenders, (
        "These break the Windows build; use pikepdf/pypdfium2 instead:\n"
        + "\n".join(offenders)
    )


def test_jbig2_is_optional():
    """The engine must import and run with no external binary present."""
    from pdfshrink import sizes  # noqa: F401


def _spy_on_subprocess(monkeypatch):
    seen = []
    original = subprocess.Popen.__init__

    def record(self, args, *rest, **kwargs):
        argv = args if isinstance(args, (list, tuple)) else [args]
        if argv:
            seen.append(os.path.basename(str(argv[0])).lower())
        return original(self, args, *rest, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "__init__", record)
    return seen


def _forbidden(seen):
    bad = []
    for name in seen:
        stem = name[:-4] if name.endswith(".exe") else name
        if stem in FORBIDDEN:
            bad.append(name)
    return bad


def test_decoding_jbig2_spawns_nothing_forbidden(jbig2_pdf, monkeypatch):
    """This is the case that slipped through: pikepdf spawning jbig2dec."""
    from pdfshrink.render import load_bilevel_pages
    seen = _spy_on_subprocess(monkeypatch)
    load_bilevel_pages(jbig2_pdf)
    assert not _forbidden(seen), "spawned: %s" % seen


def test_a_full_shrink_spawns_nothing_forbidden(bilevel_pdf, tmp_path,
                                                monkeypatch):
    import pdfshrink.core as core
    monkeypatch.setattr(core, "have_jbig2", lambda: False)
    seen = _spy_on_subprocess(monkeypatch)
    core.shrink(bilevel_pdf, str(tmp_path / "out.pdf"), target=200 * 1024)
    assert not _forbidden(seen), "spawned: %s" % seen
    for name in seen:
        stem = name[:-4] if name.endswith(".exe") else name
        assert stem in PERMITTED, "unexpected external program: %s" % name
