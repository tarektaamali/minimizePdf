from pdfshrink.render import inspect


def test_inspect_bilevel_scan(ba2):
    p = inspect(ba2)
    assert p.pages == 101
    assert p.kind == "bilevel"
    assert p.dpi == 300
    assert round(p.page_pts[0]) == 595
    assert round(p.page_pts[1]) == 841


def test_inspect_digital(digital_pdf):
    p = inspect(digital_pdf)
    assert p.kind == "digital"
    assert p.pages == 3
    assert p.has_text_layer is True


def test_inspect_colour_scan(colour_scan_pdf):
    p = inspect(colour_scan_pdf)
    assert p.kind == "raster"
    assert p.pages == 2
    assert p.dpi == 150  # 1240 px across 595 pt


import numpy as np

from pdfshrink.render import (decode_pages_ink, load_bilevel_pages,
                              render_jpeg_pages)


def test_load_bilevel_pages_shape_and_polarity(ba2):
    pages = load_bilevel_pages(ba2)
    assert len(pages) == 101
    assert pages[0].shape == (3506, 2480)
    assert pages[0].dtype == np.uint8
    ink = pages[0].mean()
    # A page of text is mostly blank, so ink must be the minority.
    assert 0.0 < ink < 0.5


def test_render_jpeg_pages(colour_scan_pdf):
    out = render_jpeg_pages(colour_scan_pdf, dpi=72, quality=60)
    assert len(out) == 2
    data, w, h = out[0]
    assert data[:2] == b"\xff\xd8"      # JPEG SOI marker
    assert (w, h) == (595, 842)


def test_decode_pages_ink_roundtrip(ba2, tmp_path):
    import pikepdf
    # Decoding is page-for-page, so excerpt rather than feed a short list:
    # a page-count mismatch is a verification failure, not a valid call.
    excerpt = str(tmp_path / "two.pdf")
    with pikepdf.open(ba2) as src:
        out = pikepdf.new()
        out.pages.extend(src.pages[:2])
        out.save(excerpt)
    pages = load_bilevel_pages(excerpt)
    shapes = [p.shape for p in pages]
    got = decode_pages_ink(excerpt, shapes)
    assert len(got) == 2
    assert got[0].shape == shapes[0]
    # Same document in, same document out: agreement must be near total.
    assert (got[0] == pages[0]).mean() > 0.98


def test_load_bilevel_pages_falls_back_when_jbig2dec_is_missing(jbig2_pdf):
    """Re-shrinking an already shrunk file must not raise DependencyError."""
    pages = load_bilevel_pages(jbig2_pdf)
    assert len(pages) == 1
    assert pages[0].shape == (64, 64)
    assert pages[0].dtype == np.uint8
    ink = float(pages[0].mean())
    assert 0.02 < ink < 0.4, ink


def test_load_bilevel_pages_still_uses_pikepdf_when_it_can(bilevel_pdf):
    pages = load_bilevel_pages(bilevel_pdf)
    assert len(pages) == 3
    assert pages[0].shape == (1754, 1240)
    assert 0.0 < float(pages[0].mean()) < 0.5


def test_a_photo_on_a_text_page_is_not_a_scan(mixed_pdf):
    """An image is only a scan when it actually covers the page.

    Comparing proportions alone misreads a mid-page photo as a full-page
    scan, and rasterising that destroys the document's live text.
    """
    p = inspect(mixed_pdf)
    assert p.kind == "digital"
    assert p.has_text_layer is True
