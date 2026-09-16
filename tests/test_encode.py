import os

import numpy as np
import pikepdf
import pytest

from pdfshrink.encode import (build_jbig2_pdf, build_jpeg_pdf, have_jbig2,
                              jbig2_encode, lossless_save, write_pbm)
from pdfshrink.render import inspect


def test_lossless_save_preserves_text(digital_pdf, tmp_path):
    dst = str(tmp_path / "out.pdf")
    size = lossless_save(digital_pdf, dst)
    assert size == os.path.getsize(dst)
    assert inspect(dst).kind == "digital"
    with pikepdf.open(dst) as pdf:
        assert len(pdf.pages) == 3


def test_build_jpeg_pdf(tmp_path):
    from pdfshrink.render import render_jpeg_pages
    src = str(tmp_path / "src.pdf")
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(595, 842))
    pdf.save(src)
    pages = render_jpeg_pages(src, dpi=72, quality=50)
    dst = str(tmp_path / "out.pdf")
    size = build_jpeg_pdf(pages, dst, (595, 842))
    assert size > 0
    with pikepdf.open(dst) as out:
        assert len(out.pages) == 1


@pytest.mark.skipif(not have_jbig2(), reason="jbig2enc not installed")
def test_build_jbig2_pdf(tmp_path):
    arr = np.zeros((200, 150), dtype=np.uint8)
    arr[50:150, 40:110] = 1
    paths = []
    for i in range(2):
        p = str(tmp_path / ("p-%04d.pbm" % i))
        write_pbm(arr, p)
        paths.append(p)
    sym, streams = jbig2_encode(paths, str(tmp_path), 0.85)
    assert sym and len(streams) == 2
    dst = str(tmp_path / "out.pdf")
    size = build_jbig2_pdf([arr.shape, arr.shape], sym, streams, dst, (595, 842))
    assert size > 0
    with pikepdf.open(dst) as out:
        assert len(out.pages) == 2


def test_g4_encode_handles_a_tall_page_as_one_strip():
    """Pillow splits tall images into strips by default; a partial strip
    yields a smaller, plausible, corrupt file, so this must not happen."""
    from pdfshrink.encode import g4_encode
    arr = np.zeros((4000, 1240), dtype=np.uint8)
    arr[100:3900, 100:1100] = 1
    data = g4_encode(arr)
    assert isinstance(data, bytes)
    assert len(data) > 0


def test_build_g4_pdf_roundtrips_with_correct_polarity(tmp_path):
    """A BlackIs1 regression shows up as near-total ink inversion."""
    import pypdfium2 as pdfium

    from pdfshrink.encode import build_g4_pdf, g4_encode

    h, w = 800, 624
    arr = np.zeros((h, w), dtype=np.uint8)
    arr[100:140, 80:540] = 1
    arr[300:700, 200:240] = 1
    expected = float(arr.mean())

    dst = str(tmp_path / "g4.pdf")
    size = build_g4_pdf([(g4_encode(arr), w, h)], dst, (595.2, 841.44))
    assert size == os.path.getsize(dst)

    doc = pdfium.PdfDocument(dst)
    pil = doc[0].render(scale=w / doc[0].get_width(), grayscale=True).to_pil()
    doc.close()
    got = float((np.array(pil.convert("L")) < 128).mean())
    assert abs(got - expected) < 0.02, (
        "ink fraction %.4f vs expected %.4f - check BlackIs1" % (got, expected))


def test_build_g4_pdf_is_recognised_as_bilevel(tmp_path):
    from pdfshrink.encode import build_g4_pdf, g4_encode

    h, w = 1754, 1240
    arr = np.zeros((h, w), dtype=np.uint8)
    arr[200:1500, 150:1100] = 1
    dst = str(tmp_path / "g4.pdf")
    build_g4_pdf([(g4_encode(arr), w, h)], dst, (595.2, 841.44))
    profile = inspect(dst)
    assert profile.kind == "bilevel"
    assert profile.dpi == 150
