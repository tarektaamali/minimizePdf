import numpy as np
import pikepdf
import pytest

from pdfshrink.verify import SUBSTITUTION_PIXELS, is_clean, verify


def test_is_clean_thresholds():
    assert is_clean((84, 85)) is True
    assert is_clean((SUBSTITUTION_PIXELS, 3)) is False
    assert is_clean((SUBSTITUTION_PIXELS + 500, 1)) is False
    assert is_clean((-1, None)) is False
    assert is_clean(None) is True      # unverifiable is not the same as dirty


def test_verify_detects_page_count_change(tmp_path):
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(595, 842))
    dst = str(tmp_path / "one.pdf")
    pdf.save(dst)
    fed = [np.zeros((100, 70), dtype=np.uint8) for _ in range(2)]
    assert verify(fed, dst) == (-1, None)


@pytest.mark.slow
def test_verify_reproduces_golden_clump(ba2, tmp_path):
    """The known-good BA2 run: 84px on page 85, below the threshold."""
    from pdfshrink.core import shrink
    dst = str(tmp_path / "out.pdf")
    result = shrink(ba2, dst, target=200 * 1024)
    assert result.ok
    assert result.check == (84, 85)
    assert is_clean(result.check)
