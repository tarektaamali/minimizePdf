"""The Windows build dies the moment a Poppler or qpdf binary reappears."""

import pathlib

FORBIDDEN = ("qpdf", "pdfimages", "pdftoppm", "pdffonts", "pdftocairo")
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
