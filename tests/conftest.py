import io
import pathlib

import pikepdf
import pytest
from PIL import Image
from pikepdf import Dictionary, Name

ROOT = pathlib.Path(__file__).parent.parent


@pytest.fixture(scope="session")
def ba2():
    """The real 101-page bilevel scan used as the golden fixture."""
    path = ROOT / "BA2.pdf"
    if not path.exists():
        pytest.skip("BA2.pdf not present")
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
