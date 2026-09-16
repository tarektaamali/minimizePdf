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
