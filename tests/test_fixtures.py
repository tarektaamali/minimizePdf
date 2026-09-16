"""A fixture that is silently the wrong document is worse than a missing one."""

import pytest

from conftest import GOLDEN_BYTES, GOLDEN_PAGES, check_golden


def test_check_golden_rejects_the_wrong_document(digital_pdf):
    with pytest.raises(AssertionError) as caught:
        check_golden(digital_pdf)
    assert "BA2.pdf" in str(caught.value)


def test_golden_constants_match_the_measured_original():
    assert GOLDEN_BYTES == 1687366
    assert GOLDEN_PAGES == 101


def test_bilevel_fixture_is_seen_as_bilevel(bilevel_pdf):
    from pdfshrink.render import inspect
    profile = inspect(bilevel_pdf)
    assert profile.kind == "bilevel"
    assert profile.pages == 3
    assert profile.dpi == 150
