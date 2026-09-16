import io
import pathlib

import pikepdf
import pytest
from PIL import Image
from pikepdf import Dictionary, Name

ROOT = pathlib.Path(__file__).parent.parent

GOLDEN_BYTES = 1687366
GOLDEN_PAGES = 101


def check_golden(path):
    """Fail loudly when a present BA2.pdf is not the measured original."""
    path = pathlib.Path(path)
    size = path.stat().st_size
    assert abs(size - GOLDEN_BYTES) <= GOLDEN_BYTES * 0.05, (
        "BA2.pdf is present but is not the golden original: %d bytes, "
        "expected about %d. The 197 Ko file is this tool's OUTPUT, not its "
        "input. Remove it or replace it with the 1648 Ko, 300 dpi scan."
        % (size, GOLDEN_BYTES))
    with pikepdf.open(str(path)) as pdf:
        pages = len(pdf.pages)
    assert pages == GOLDEN_PAGES, (
        "BA2.pdf is present but has %d pages, expected %d; this is not the "
        "golden original." % (pages, GOLDEN_PAGES))


@pytest.fixture(scope="session")
def ba2():
    """The real 101-page bilevel scan used as the golden fixture."""
    path = ROOT / "BA2.pdf"
    if not path.exists():
        pytest.skip("BA2.pdf not present")
    check_golden(path)
    return str(path)


@pytest.fixture
def digital_pdf(tmp_path):
    """Real fonts, no images. Must never be rasterised."""
    pdf = pikepdf.new()
    font = pdf.make_indirect(Dictionary(
        Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica))
    for n in range(3):
        page = pdf.add_blank_page(page_size=(595, 842))
        page.Resources = Dictionary(Font=Dictionary(F1=font))
        page.Contents = pdf.make_stream(
            b"BT /F1 24 Tf 72 700 Td (Bonjour page %d) Tj ET" % n)
    out = tmp_path / "digital.pdf"
    pdf.save(str(out))
    return str(out)


@pytest.fixture
def colour_scan_pdf(tmp_path):
    """Full-page 8-bit colour images, no fonts."""
    pdf = pikepdf.new()
    for n in range(2):
        im = Image.new("RGB", (1240, 1754))
        im.paste((200, 30 + n * 40, 90), (0, 0, 600, 900))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=80)
        stream = pdf.make_stream(buf.getvalue())
        stream.Type = Name.XObject
        stream.Subtype = Name.Image
        stream.Width, stream.Height = im.size
        stream.ColorSpace = Name.DeviceRGB
        stream.BitsPerComponent = 8
        stream.Filter = Name.DCTDecode
        page = pdf.add_blank_page(page_size=(595, 842))
        page.Contents = pdf.make_stream(b"q 595 0 0 842 0 0 cm /Im0 Do Q")
        page.Resources = Dictionary(XObject=Dictionary(Im0=stream))
    out = tmp_path / "colour.pdf"
    pdf.save(str(out))
    return str(out)


@pytest.fixture
def bilevel_pdf(tmp_path):
    """Three 1-bit full-page images at 150 dpi, uncompressed.

    Uncompressed rather than G4 so it does not depend on the encoder it is
    used to test, and so pikepdf can extract it without any external binary.
    """
    import numpy as np

    w, h = 1240, 1754                      # 150 dpi A4, width divisible by 8
    pdf = pikepdf.new()
    for n in range(3):
        ink = np.zeros((h, w), dtype=bool)
        for row in range(120, h - 120, 46):
            ink[row:row + 14, 100:w - 100 - (n * 60)] = True
            ink[row:row + 14, 300::97] = False
        packed = np.packbits(~ink, axis=1).tobytes()   # 0 = black
        stream = pdf.make_stream(packed)
        stream.Type = Name.XObject
        stream.Subtype = Name.Image
        stream.Width, stream.Height = w, h
        stream.ColorSpace = Name.DeviceGray
        stream.BitsPerComponent = 1
        page = pdf.add_blank_page(page_size=(595.2, 841.44))
        page.Contents = pdf.make_stream(b"q 595.2 0 0 841.44 0 0 cm /Im0 Do Q")
        page.Resources = Dictionary(XObject=Dictionary(Im0=stream))
    out = tmp_path / "bilevel.pdf"
    pdf.save(str(out))
    return str(out)


@pytest.fixture
def jbig2_pdf():
    """A minimal JBIG2 PDF. pikepdf cannot decode it without jbig2dec."""
    path = ROOT / "tests" / "fixtures" / "jbig2_min.pdf"
    if not path.exists():
        pytest.skip("run scripts/make_jbig2_fixture.py")
    return str(path)
