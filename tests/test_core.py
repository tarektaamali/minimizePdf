import os

import pytest

from pdfshrink.core import shrink
from pdfshrink.verify import is_clean


def test_digital_pdf_is_never_rasterised(digital_pdf, tmp_path):
    from pdfshrink.render import inspect
    dst = str(tmp_path / "out.pdf")
    result = shrink(digital_pdf, dst, target=1024 * 1024)
    assert result.ok
    assert inspect(dst).kind == "digital"


def test_digital_pdf_refuses_impossible_target(digital_pdf, tmp_path):
    dst = str(tmp_path / "out.pdf")
    result = shrink(digital_pdf, dst, target=64)
    assert result.ok is False
    assert result.reason == "digital_floor"
    assert result.best_safe_size is not None


def test_colour_scan_uses_raster_ladder(colour_scan_pdf, tmp_path):
    dst = str(tmp_path / "out.pdf")
    result = shrink(colour_scan_pdf, dst, target=60 * 1024)
    assert result.ok
    assert result.size <= 60 * 1024
    assert result.dpi is not None


def test_progress_callback_reports_stages(colour_scan_pdf, tmp_path):
    seen = []
    shrink(colour_scan_pdf, str(tmp_path / "o.pdf"), target=60 * 1024,
           progress=lambda stage, done, total: seen.append(stage))
    assert "inspect" in seen
    assert "compress" in seen


@pytest.mark.slow
def test_ba2_golden_run(ba2, tmp_path):
    """Matches the measured probe exactly. Guards against regression."""
    dst = str(tmp_path / "out.pdf")
    result = shrink(ba2, dst, target=200 * 1024)
    assert result.ok is True
    assert result.size <= 200 * 1024
    assert os.path.getsize(dst) == result.size
    assert result.dpi == 150
    assert result.check == (84, 85)
    assert is_clean(result.check)
    assert result.before == 1687366


@pytest.mark.slow
def test_ba2_impossible_target_offers_best_safe(ba2, tmp_path):
    dst = str(tmp_path / "out.pdf")
    result = shrink(ba2, dst, target=50 * 1024)
    assert result.ok is False
    assert result.reason == "too_large"
    assert result.best_safe_size > 50 * 1024
    assert os.path.getsize(dst) == result.best_safe_size


def test_bilevel_without_jbig2_uses_g4_not_jpeg(bilevel_pdf, tmp_path,
                                                monkeypatch):
    """The JPEG path floors around 3827 Ko for a scan; G4 must be used."""
    import pikepdf

    import pdfshrink.core as core
    monkeypatch.setattr(core, "have_jbig2", lambda: False)
    dst = str(tmp_path / "out.pdf")
    result = core.shrink(bilevel_pdf, dst, target=200 * 1024)
    assert result.ok is True
    assert result.size <= 200 * 1024

    with pikepdf.open(dst) as pdf:
        image = pdf.pages[0]["/Resources"]["/XObject"]["/Im0"]
        assert str(image.Filter) == "/CCITTFaxDecode"


def test_g4_sizes_decrease_as_dpi_decreases(bilevel_pdf, tmp_path,
                                            monkeypatch):
    """An inverted size trend is the first sign of a broken encoder."""
    import pdfshrink.core as core
    monkeypatch.setattr(core, "have_jbig2", lambda: False)
    dst = str(tmp_path / "out.pdf")
    result = core.shrink(bilevel_pdf, dst, target=1, min_dpi=50)
    sizes = [size for _, _, size in result.attempts]
    assert len(sizes) >= 3
    assert sizes == sorted(sizes, reverse=True), sizes


def test_g4_refuses_an_impossible_target(bilevel_pdf, tmp_path, monkeypatch):
    import pdfshrink.core as core
    monkeypatch.setattr(core, "have_jbig2", lambda: False)
    dst = str(tmp_path / "out.pdf")
    result = core.shrink(bilevel_pdf, dst, target=1, min_dpi=50)
    assert result.ok is False
    assert result.reason == "too_large"
    assert result.best_safe_size == os.path.getsize(dst)


def test_g4_never_runs_the_substitution_check(bilevel_pdf, tmp_path,
                                              monkeypatch):
    """G4 cannot substitute a glyph; checking would cause false refusals."""
    import pdfshrink.core as core
    called = []
    monkeypatch.setattr(core, "have_jbig2", lambda: False)
    monkeypatch.setattr(core, "verify",
                        lambda *a, **k: called.append(a) or (0, None))
    core.shrink(bilevel_pdf, str(tmp_path / "out.pdf"), target=200 * 1024)
    assert called == []
