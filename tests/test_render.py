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
